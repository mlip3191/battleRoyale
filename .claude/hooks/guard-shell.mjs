#!/usr/bin/env node
// PreToolUse guard for the Bash and PowerShell tools.
// Reads the tool input JSON from stdin and blocks (exit 2, reason on stderr) commands that
// could leak secrets, lose work, or bypass the team's git rules. Any internal error also
// blocks: a guard that crashes must fail closed.
import { execFileSync } from "node:child_process";

const SECRET_MSG = "Claude isn't allowed to read or change secret files. Ask the PM.";

// Block with a plain-English reason and stop.
function block(reason) {
  process.stderr.write(`Blocked by guard-shell: ${reason}\n`);
  process.exit(2);
}

// Read all of stdin as text.
async function readStdin() {
  let data = "";
  for await (const chunk of process.stdin) data += chunk;
  return data;
}

// Split a command line into segments of tokens, respecting quotes.
// Segments break on ; & | && || newlines, parentheses, and backticks outside quotes.
// Commands inside $( ) or backticks within double quotes are returned as nested strings.
// Heredoc bodies are skipped (they are data, not commands).
function parse(command) {
  const segments = [];
  const nested = [];
  let tokens = [];
  let cur = "";
  let hasCur = false;
  let quote = null;
  const heredocs = [];

  const endToken = () => {
    if (hasCur) tokens.push(cur);
    cur = "";
    hasCur = false;
  };
  const endSegment = () => {
    endToken();
    if (tokens.length) segments.push(tokens);
    tokens = [];
  };
  // Capture a $( ) or backtick body starting at i; return the index after it.
  const capture = (i, open, close) => {
    let depth = 1;
    let j = i;
    for (; j < command.length; j++) {
      if (open && command.startsWith(open, j)) depth++;
      else if (command[j] === close && --depth === 0) break;
    }
    nested.push(command.slice(i, j));
    return j;
  };

  for (let i = 0; i < command.length; i++) {
    const c = command[i];
    if (quote === "'") {
      if (c === "'") quote = null;
      else cur += c;
      continue;
    }
    if (quote === '"') {
      if (c === "\\" && i + 1 < command.length) cur += command[++i];
      else if (c === '"') quote = null;
      else if (c === "$" && command[i + 1] === "(") i = capture(i + 2, "$(", ")");
      else if (c === "`") i = capture(i + 1, null, "`");
      else cur += c;
      continue;
    }
    if (c === "'" || c === '"') {
      quote = c;
      hasCur = true;
      continue;
    }
    if (c === "\\" && command[i + 1] === "\n") {
      endToken();
      i += 1;
      continue;
    }
    if (c === "\\" && i + 1 < command.length) {
      cur += command[++i];
      hasCur = true;
      continue;
    }
    if (c === "<" && command[i + 1] === "<" && command[i + 2] !== "<") {
      // Heredoc: remember its delimiter so the body is skipped after the next newline.
      endToken();
      let j = i + 2;
      const strip = command[j] === "-";
      if (strip) j++;
      while (command[j] === " ") j++;
      const m = /^(['"]?)([A-Za-z0-9_.-]+)\1/.exec(command.slice(j));
      if (m) {
        heredocs.push({ delim: m[2], strip });
        i = j + m[0].length - 1;
      } else {
        i += 1;
      }
      continue;
    }
    if (c === "\n") {
      endSegment();
      while (heredocs.length) {
        const { delim, strip } = heredocs.shift();
        let j = i + 1;
        for (;;) {
          const nl = command.indexOf("\n", j);
          const line = command.slice(j, nl === -1 ? command.length : nl);
          j = nl === -1 ? command.length : nl + 1;
          if ((strip ? line.trim() : line) === delim || nl === -1) break;
        }
        i = j - 1;
      }
      continue;
    }
    if (c === "$" && command[i + 1] === "(") {
      endSegment();
      i += 1;
      continue;
    }
    if (";&|()`".includes(c)) {
      endSegment();
      continue;
    }
    if (c === " " || c === "\t" || c === "\r") {
      endToken();
      continue;
    }
    cur += c;
    hasCur = true;
  }
  if (quote) throw new Error("unterminated quote");
  endSegment();
  return { segments, nested };
}

// Strip wrappers like sudo, env VAR=1, command, nohup so the real command is checked.
function unwrap(tokens) {
  let t = tokens.slice();
  for (;;) {
    if (!t.length) return t;
    const head = t[0].toLowerCase();
    if (/^[A-Za-z_][A-Za-z0-9_]*=/.test(t[0])) t = t.slice(1);
    else if (["sudo", "command", "nohup", "time", "exec", "builtin"].includes(head)) t = t.slice(1);
    else if (head === "env") {
      let r = t.slice(1);
      while (r.length && (r[0].startsWith("-") || /^[A-Za-z_][A-Za-z0-9_]*=/.test(r[0]))) r = r.slice(1);
      if (!r.length) return t;
      t = r;
    } else return t;
  }
}

// The last path component of a token, after removing redirections, = prefixes, and punctuation.
function lastComponent(token) {
  let s = token.replace(/^[0-9]*[<>]+&?/, "");
  if (s.includes("=")) s = s.slice(s.lastIndexOf("=") + 1);
  s = s.replace(/^[(){}'"`]+|[(){}'"`;,]+$/g, "");
  const parts = s.split(/[\\/]/);
  return parts[parts.length - 1].toLowerCase();
}

// True when a whitespace-free token names a secret file (.env files, keys).
function isSecretPath(token) {
  if (/\s/.test(token)) return false;
  const name = lastComponent(token);
  if (!name) return false;
  if ([".env.example", ".env.sample", ".env.template"].includes(name)) return false;
  if (name === ".env" || name.startsWith(".env.")) return true;
  return name.endsWith(".env") || name.endsWith(".pem") || name.endsWith(".key");
}

// True when a long option is the option itself or an abbreviation git would accept.
function isLongOpt(arg, full) {
  const name = arg.split("=")[0];
  return name.length >= 4 && full.startsWith(name);
}

// True when a short-flag cluster like -fA contains the letter.
function hasShort(arg, letter) {
  return /^-[A-Za-z]+$/.test(arg) && arg.slice(1).includes(letter);
}

// Current branch of the repo in dir, or "" when unknown.
function currentBranch(dir) {
  try {
    return execFileSync("git", ["-C", dir, "branch", "--show-current"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return "";
  }
}

// Split git's global options from the subcommand; return { dir, configs, sub, args }.
function parseGit(args, cwd) {
  let dir = cwd;
  const configs = [];
  let i = 0;
  while (i < args.length && args[i].startsWith("-")) {
    const a = args[i];
    if (a === "-C") dir = args[++i] ?? dir;
    else if (a === "-c") configs.push(args[++i] ?? "");
    else if (a.startsWith("--config-env")) configs.push(a.includes("=") ? a : (args[++i] ?? ""));
    else if (["--git-dir", "--work-tree", "--namespace"].includes(a)) i++;
    i++;
  }
  return { dir, configs, sub: (args[i] ?? "").toLowerCase(), args: args.slice(i + 1) };
}

// Check one git invocation against the team rules.
function checkGit(args, cwd) {
  const { dir, configs, sub, args: rest } = parseGit(args, cwd);
  if (configs.some((c) => /^core\.hookspath/i.test(c))) {
    block("changing core.hooksPath switches off the team's secret guard.");
  }
  if (sub === "config" && rest.some((a) => /^core\.hookspath$/i.test(a))) {
    block("changing core.hooksPath switches off the team's secret guard.");
  }
  if (sub === "commit") checkCommit(rest, dir);
  if (sub === "push") checkPush(rest, dir);
  if (sub === "add" && rest.some((a) => hasShort(a, "f") || isLongOpt(a, "--force"))) {
    block("git add -f/--force would add ignored files such as .env. Don't force-add files.");
  }
  if (sub === "reset" && rest.some((a) => isLongOpt(a, "--hard"))) {
    block("git reset --hard throws away uncommitted work. Ask the user and use a safer command.");
  }
  if (sub === "clean") {
    block("git clean deletes untracked files (with -x it deletes .env). Not allowed.");
  }
  if (sub === "branch") {
    const del = rest.some((a) => hasShort(a, "d") || isLongOpt(a, "--delete"));
    const force = rest.some((a) => hasShort(a, "f") || isLongOpt(a, "--force"));
    if (rest.some((a) => hasShort(a, "D")) || (del && force)) {
      block("git branch -D force-deletes a branch and can lose work. The PM does this by hand.");
    }
  }
  if (sub === "checkout" && (rest.includes("--") || rest.includes("."))) {
    block("git checkout -- <path> / git checkout . discards uncommitted changes.");
  }
  if (sub === "restore") {
    const staged = rest.some((a) => hasShort(a, "S") || isLongOpt(a, "--staged"));
    const worktree = rest.some((a) => hasShort(a, "W") || isLongOpt(a, "--worktree"));
    if (!staged || worktree) {
      block("git restore without --staged discards uncommitted changes. Use git restore --staged.");
    }
  }
}

// git commit: never on main, never skip the pre-commit hook.
function checkCommit(args, dir) {
  const takesValue = ["-m", "-F", "-C", "-c", "-t", "--message", "--file", "--author", "--date",
    "--template", "--fixup", "--squash", "--trailer", "--cleanup", "--reuse-message",
    "--reedit-message"];
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (takesValue.includes(a)) {
      i++;
      continue;
    }
    if (isLongOpt(a, "--no-verify") || (/^-[A-Za-z]+$/.test(a) && hasShort(a, "n"))) {
      block("git commit --no-verify/-n skips the team's secret check. Never skip it.");
    }
  }
  if (currentBranch(dir) === "main") {
    block("no commit on main. Create a branch first: git switch -c issue-<number>-short-description");
  }
}

// git push: never to main, never force, never delete remote branches.
function checkPush(args, dir) {
  const positional = [];
  const takesValue = ["--repo", "--receive-pack", "--exec", "-o", "--push-option"];
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a.startsWith("-")) {
      if (hasShort(a, "f") || isLongOpt(a, "--force") || isLongOpt(a, "--force-with-lease") ||
          isLongOpt(a, "--force-if-includes")) {
        block("force pushing can erase teammates' work. Not allowed.");
      }
      if (hasShort(a, "d") || isLongOpt(a, "--delete")) {
        block("deleting remote branches isn't allowed (GitHub deletes merged branches itself).");
      }
      if (isLongOpt(a, "--all") || isLongOpt(a, "--mirror")) {
        block("git push --all/--mirror would push main. Push only your issue branch.");
      }
      if (takesValue.includes(a)) i++;
      continue;
    }
    positional.push(a);
  }
  const refspecs = positional.slice(1);
  for (const ref of refspecs) {
    if (ref.startsWith("+")) block("a +refspec is a force push. Not allowed.");
    if (ref.startsWith(":")) block("a :branch refspec deletes a remote branch. Not allowed.");
    const target = (ref.includes(":") ? ref.slice(ref.indexOf(":") + 1) : ref).replace(/^refs\/heads\//, "");
    const pushesCurrent = ["HEAD", "@"].includes(ref.split(":")[0]) && !ref.includes(":");
    if (target === "main" || (pushesCurrent && currentBranch(dir) === "main")) {
      block("no pushing to main. Push your issue branch and open a pull request.");
    }
  }
  if (refspecs.length === 0 && currentBranch(dir) === "main") {
    block("no pushing to main. Push your issue branch and open a pull request.");
  }
}

// rm with recursive + force in any spelling; PowerShell Remove-Item -Recurse and its aliases.
function checkRemove(cmd, args) {
  if (cmd === "rm") {
    const recursive = args.some((a) => hasShort(a, "r") || hasShort(a, "R") || isLongOpt(a, "--recursive"));
    const force = args.some((a) => hasShort(a, "f") || isLongOpt(a, "--force"));
    if (recursive && force) block("rm -rf (recursive + force delete) isn't allowed. Ask the user.");
  }
  if (["remove-item", "ri", "del", "erase", "rd", "rmdir", "rm"].includes(cmd)) {
    const minLen = cmd === "rm" ? 4 : 2;
    if (args.some((a) => a.length >= minLen && "-recurse".startsWith(a.toLowerCase()))) {
      block("Remove-Item -Recurse isn't allowed. Ask the user.");
    }
  }
}

// Printing environment variables would show keys.
function checkEnvDump(cmd, args, tokens) {
  if (cmd === "printenv") block("printing environment variables could show keys.");
  if (cmd === "env" && args.every((a) => a.startsWith("-"))) block("printing environment variables could show keys.");
  if (tokens.some((t) => /\$env:/i.test(t) || (!/\s/.test(t) && /^env:/i.test(t)))) {
    block("reading PowerShell env: variables could show keys.");
  }
}

// Shells and eval run their string argument as a command, so check it too.
function innerCommands(cmd, args) {
  if (cmd === "eval") return [args.join(" ")];
  const shells = ["sh", "bash", "zsh", "dash", "pwsh", "powershell", "cmd"];
  if (!shells.includes(cmd.replace(/\.exe$/, ""))) return [];
  const out = [];
  for (let i = 0; i < args.length; i++) {
    if (/^(-c|-command|\/c|\/k)$/i.test(args[i]) && args[i + 1] !== undefined) out.push(args.slice(i + 1).join(" "));
  }
  return out;
}

// Check a whole command line, including nested commands.
function checkCommand(command, cwd, depth = 0) {
  if (depth > 5) block("command nesting is too deep to check safely.");
  const { segments, nested } = parse(command);
  for (const raw of segments) {
    const tokens = unwrap(raw);
    if (!tokens.length) continue;
    if (raw.some(isSecretPath)) block(SECRET_MSG);
    const cmd = lastComponent(tokens[0]).replace(/\.exe$/, "");
    const args = tokens.slice(1);
    if (cmd === "node" && args[0] === "scripts/check-env.mjs") continue;
    if (cmd === "git") checkGit(args, cwd);
    checkRemove(cmd, args);
    checkEnvDump(cmd, args, raw);
    for (const inner of innerCommands(cmd, args)) checkCommand(inner, cwd, depth + 1);
  }
  for (const inner of nested) checkCommand(inner, cwd, depth + 1);
}

try {
  const input = JSON.parse(await readStdin());
  const command = input?.tool_input?.command;
  if (typeof command !== "string") throw new Error("no command in tool input");
  const cwd = input.cwd || process.env.CLAUDE_PROJECT_DIR || process.cwd();
  checkCommand(command, cwd);
  process.exit(0);
} catch (err) {
  process.stderr.write(`guard error — blocked to be safe (${err?.message ?? err})\n`);
  process.exit(2);
}
