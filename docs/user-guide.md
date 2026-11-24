# Battle Royale user guide

This guide is for someone who has never seen the app, and maybe never used a terminal. It takes about 30 minutes the first time, mostly waiting for installs.

**Contents:** [1. What it is](#1-what-the-app-does) · [2. Run it](#2-run-it-on-your-computer) · [3. Use it](#3-use-it) · [4. What it won't do](#4-what-it-wont-do) · [5. Troubleshooting](#5-troubleshooting)

---

## 1. What the app does

You name two sides of an imaginary fight, like *"a grizzly bear vs 6 gray wolves in a forest"*. The app looks up each fighter in vetted sources (mostly Wikipedia and published studies) and builds a stat sheet, then runs the fight about 1,000 times in a simulation to decide who usually wins. It plays the result as a corny late-night sports broadcast, then shows the full results with every source.

**What "science-backed" means here:**

- **Sourced stats.** Every sourced number on a stat sheet links to the page it came from, along with the exact quote. An AI model may copy a number only together with that quote, and code checks that the number really is in it.
- **Labeled guesses.** When no source gives a number, the app uses a default for that kind of fighter and tags it **estimate**. Traits that no source measures (aggression, armor, teamwork) are tagged **assumption** and come from a written scale.
- **Code decides the winner.** A simulation written in plain code picks the winner, not an AI model. The same matchup always gives the same result.

## 2. Run it on your computer

The app runs on your own computer and opens in your web browser. It works the same on Windows and Mac. You need an internet connection.

**Opening a terminal:** a terminal is a window where you type commands.

- **Windows:** press the Windows key, type **PowerShell**, and press Enter.
- **Mac:** press Cmd+Space, type **Terminal**, and press Enter.

Type each command below exactly, then press Enter, and wait for it to finish before typing the next one.

> **Windows tip:** if PowerShell says *"running scripts is disabled on this system"* when you type `npm`, type `npm.cmd` instead of `npm` in every command (for example `npm.cmd start`). See [Troubleshooting](#5-troubleshooting).

### Step 1: Install Node 26, uv and Git

Node runs the web page, uv runs the Python back end (it installs the right Python for you), and Git downloads the code.

| | Windows | Mac |
|---|---|---|
| **Node 26** | Download the installer from [nodejs.org](https://nodejs.org) and click through it. On the "Tools for Native Modules" screen, leave the box **unchecked**. | Download the installer from [nodejs.org](https://nodejs.org), or `brew install fnm` then `fnm install 26` |
| **uv** | `winget install astral-sh.uv` | `brew install uv` |
| **Git** | `winget install Git.Git` | `xcode-select --install` (or `brew install git`) |

**Close the terminal and open a new one** so it finds the new programs. Then check them:

```bash
node --version
```

```bash
uv --version
```

You should see `v26` and a uv version number:

![Terminal showing node --version printing v26.13.0 and uv --version printing a version](images/user-guide/01-versions.png)

### Step 2: Get the code

Clone it with Git:

```bash
git clone https://github.com/mlip3191/battleRoyale.git
```

Then move the terminal into that folder:

```bash
cd battleRoyale
```

![Terminal showing git clone downloading the project into a battleRoyale folder, then cd battleRoyale](images/user-guide/01b-clone.png)

> **No Git?** On the project's GitHub page you can click the green **Code** button, then **Download ZIP**, and unzip it somewhere easy. To move the terminal into that folder, type `cd ` (with a space), drag the folder from File Explorer or Finder onto the terminal window, and press Enter. Everything works the same, and you don't need Git. At the end, `npm run setup` (step 4) says *"Not a git checkout (a ZIP copy?), so the commit guard was skipped"*. That's expected: the guard only matters for people changing the code.

### Step 3: Connect the course AI endpoints (optional)

The app uses AI models provided by the course. Skip this step to try the app in **mock mode**: it runs with built-in sample data and needs no endpoints or key. The fights are still real simulations, but the fighters' stats, pictures and commentary are stand-ins.

To use the real AI endpoints, run:

```bash
npm run env:setup
```

It asks two questions. Paste in the **course host** and the **course API key** from the course endpoint list. Both come from the course, not from this project: use the endpoint list in the course materials your instructor shared, and if you can't find it, ask your instructor or a teammate. The key stays hidden while you type or paste it. Your answers are saved only in a file called `.env` on your computer, and the app switches to live mode.

![Terminal showing npm run env:setup asking for the course host and a hidden API key, then saving to .env](images/user-guide/02-env-setup.png)

Never paste the key into a chat, an email, or a GitHub page. To check your settings later without showing them, run `npm run env:check`.

### Step 4: Install the app

```bash
npm run setup
```

This downloads everything the app needs. It takes a minute or two the first time. Warnings such as "packages are looking for funding", "vulnerabilities" or, on a Mac, `npm warn install-scripts … fsevents` are normal and can be ignored.

![Terminal showing npm run setup installing packages and finishing](images/user-guide/03-setup.png)

### Step 5 (optional): Refresh the knowledge base

You can usually skip this step. The app comes with a ready-made knowledge base (the reference articles it researches fighters from), and in live mode it loads it the first time it starts: at step 6 the terminal says "Loaded the prebuilt knowledge base (3299 passages from 30 articles)". In mock mode (you skipped step 3) it isn't needed at all.

Run this only to refresh the articles, or if the app says your embedding model differs from the one that built the prebuilt knowledge base:

```bash
npm run ingest
```

It downloads the reference articles the app researches fighters from. It takes a while (about half an hour on a laptop), and it's quiet for long stretches, so let it run. Lines like "Parser skipped…" and "No trait match…" are normal. It's done when it prints a table and "Finished in … s". A few more "No trait match…" lines may print after that; it's still done. You only need it once, not every time you start the app.

![Terminal showing npm run ingest finishing with a table: 30 fighters, 30 documents, 0 failures, then "Finished in 1814 s."](images/user-guide/03b-ingest.png)

### Step 6: Start the app

```bash
npm start
```

Wait until you see **"Battle Royale is starting at http://localhost:8000"** and **"Application startup complete"**. Leave this window open: closing it stops the app.

![Terminal showing npm start building the page and then "Battle Royale is starting at http://localhost:8000"](images/user-guide/04-start.png)

### Step 7: Open the app

Open your web browser (Chrome, Edge, Safari or Firefox) and go to **http://localhost:8000**.

![The Battle Royale home page: "Who would win?" with a text box, a FIGHT! button, the "Stumped? Try one of the sample battles below" example matchups and the "Showcase (Ready Made)" battles](images/user-guide/05-home.png)

On the battle and results pages, a **Home** button in the top bar brings you back here.

**To stop the app:** click the terminal window and press **Ctrl+C**. To start it again later, open a terminal in the same folder and run `npm start`. You don't need to repeat steps 1 to 5.

## 3. Use it

### Type a matchup

The instructions sit right under the heading. Type two sides into the box, with how many of each and, if you like, a place. Then press Enter or click **FIGHT!**. You can also click one of the example matchups under **Stumped? Try one of the sample battles below**, below the box: it fills in the box, and then you click **FIGHT!**. An example starts a new fight, researched and simulated live, so it takes about a minute or two.

Good examples:

- `a grizzly bear vs 6 gray wolves in a forest`
- `10 duck-sized horses vs 1 horse-sized duck`
- `a honey badger vs a king cobra`
- `a saltwater crocodile vs a horse in the water`

Counts can be numbers or words ("a dozen house cats"), up to 10,000 per side. Size phrases like "horse-sized duck" work too: the app scales the duck up using both animals' real weights.

**Fighters that work best today:** the app has hand-checked stat sheets for 15 fighters: African elephant, African lion, bald eagle, bulldozer, duck, gorilla, gray wolf, grizzly bear, honey badger, horse, house cat, king cobra, main battle tank, Roman legionary, and saltwater crocodile. Any other fighter still gets a battle, but its stats are estimates, not looked up. An animal that isn't on the list fights back, but on generic estimated stats, so treat its result as a rough guess (a polar bear counts as about one gray wolf). A name the app can't place, or one it isn't allowed to use, is called off with a friendly message instead.

![The matchup "a bear vs 6 wolves in a forest" typed into the box](images/user-guide/06-typed.png)

### Answer the quick question

If a fighter is vague, the app asks **one** question, such as *"Which type of bear would you like?"*. Click an answer, or type your own and click **Answer**. If your answer is still vague, the app picks the most common kind and tells you what it assumed.

![The "Quick question" card asking which type of bear, with buttons for Grizzly, Polar, American Black and Asian Black](images/user-guide/07-question.png)

### Check tonight's card and pick a battlefield

The page scrolls down to the card, which shows how the app read your matchup: each side, how many, and any assumptions it made. Pick a **Battlefield** from the list (arena, open field, forest, open water, shoreline, city streets, mountain or sky), then click **Start the fight!** on the card. In the **sky**, fliers fight each other; a fighter on the ground can only reach a flier with a ranged attack (a rifle, or a breath weapon on a creature that can't fly), so "a bald eagle vs a grizzly bear in the sky" is a no contest.

![The "Tonight's card" panel showing Bear (grizzly) vs 6 × Wolf (gray), the Battlefield set to Forest, and a Start the fight! button](images/user-guide/08-card.png)

### Watch the broadcast

While the app researches and simulates, a ticker shows what it's doing and a list shows each step's progress. This usually takes under a minute. Recording the announcer's voice can take about another minute; the ticker says so while it runs, and the show starts as soon as the voice is ready.

![The broadcast page while it works: "Researching the bear…" with each step listed as done, running or pending](images/user-guide/09-loading.png)

Then the show starts: the announcer introduces the fighters, with captions on screen. The intro has its own **Start the fight** button (a second one, after the card's): click it when you're ready, or **Skip to verdict** to jump straight to the result. A note may appear at the top. **"Some effects unavailable: …"** names the parts that used a stand-in this time (for example the voice or the pictures; music is cut, so it is never listed); **"Some commentary used the template script"** means the AI announcer was slow, so ready-made commentary was used. Either way the captions always carry the show, and the fight and its numbers are the same.

![The intro: Grizzly bear VS 6 gray wolves, an announcer caption, and Start the fight and Skip to verdict buttons](images/user-guide/10-intro.png)

The fight replays one of the simulated fights. The floating minus numbers are damage from the simulation's own log, and each side's health bar drops with every hit: it shows the side's combined hit points left, and a group also shows how many are still standing. Use **Pause**, **1×**, **2×**, **5×** and **10×** to control the speed, or **Skip to end**. The announcer says each moment's lines as the fight reaches them: it pauses when you pause, talks faster at 2×, and waits at 5× and 10× until you slow back down. The captions keep going either way. Sound turns on when you click **Start the fight**; the **Sound on / Sound off** button and a volume slider control the announcer's voice, and switching sound off is remembered for this visit, so later fights in the same browser tab start silent until you switch it back on; a new tab or visit starts with sound. Switching sound on partway through a moment finishes that moment's lines. The captions always carry the show, with or without sound.

![The animated fight: a grizzly bear facing six wolves in a pixel-art forest, with a damage number above the bear](images/user-guide/11-fight.jpg)

At the end, the verdict shows the winner, their win chance, and the reason in one line. When the fight is nearly 50/50 (the win range reaches 50%), it says **"Too close to call"** with a slight edge to one side instead of crowning a winner, on the card, the reveal and the arena.

![The verdict: "Winner: 6 gray wolves!", win chance 78% with range 75–80% over 1,000 simulated fights, and the deciding factor: numbers decided it](images/user-guide/12-verdict.jpg)

### Read the results page

Click **See the full results**. Each part, top to bottom:

- **Win chance and range.** For example "78% – range 75–80%". The app runs about 1,000 fights, and each one draws the fighters' stats from within their known range. The range shows how sure the result is, given how uncertain the stats are. It also shows how many fighters are usually left standing and how long fights last.
- **Deciding factor.** The one thing that mattered most, such as numbers, size, speed or armor. Code finds it by testing which stat changes the result most.

![The top of the results page: winner, win chance and range for each side, draw chance, average fight length, and the deciding factor](images/user-guide/13-results-verdict.png)

- **Fair fight.** How many of the losing side it would take to make the odds about even, for example "about 2 grizzly bears against 6 gray wolves". If no count up to 10,000 gets close, it says so.
- **Next challenger.** A suggested opponent for the winner. Click **Fight them!** to start that fight right away.

![Under the verdict: the fair fight, the next challenger with a Fight them! button, then the start of the tale of the tape](images/user-guide/15-results-fair-fight.png)

- **Tale of the tape.** One stat sheet per fighter. For each stat you see the value and where it comes from:
  - a **source link** with a confidence level and a short note from the source;
  - an **estimate** tag when no source had the number, so the app used a default for that kind of fighter;
  - a **derived** tag when code worked it out from other stats (for example, reach from size);
  - an **assumption** tag for traits no source measures, set from a written scale.

  A yellow "Heads up" banner warns you when many stats on a sheet are estimates or assumptions.

![A stat sheet for the grizzly bear: mass, size and top speed with Wikipedia source links, and estimate, derived and assumption tags on other stats](images/user-guide/14-results-tape.png)

- **Sources.** Every page the stats came from, with links and licenses.

**Sharing:** the address in your browser's address bar reopens this result. It works on your own computer while the app is running.

### Showcase battles

Ready-made battles show off what the app can do. They load automatically when the app starts and appear under **Showcase (Ready Made)** on the home page. Unlike the examples above the box, they're saved battles: click one to watch it straight away, with no waiting:

1. 100 duck-sized horses vs 1 horse-sized duck
2. Grizzly bear vs 4 gray wolves
3. Honey badger vs king cobra
4. Roman legionary vs gorilla
5. Dragon vs main battle tank

## 4. What it won't do

The app politely turns some requests away, and tells you why:

| It won't use | Why | What you'll see |
|---|---|---|
| **Real people** (alive or historical) | It's not fair or kind to stage fights between real people. | "We keep real people out of the ring. Try a type of fighter instead, like a Roman legionary or a medieval knight." |
| **Named characters**, from stories or from myth | They belong to their creators or their legends, and they have no real-world stats to look up. | "Named characters, from stories or from myth, sit this one out. Try a creature type instead, like a dragon or a giant robot." |
| **Gods and figures of living religions** (Allah, Jesus, Shiva, the Pope) | They matter to many people. Gods of mythology (Zeus, Thor) and generic kinds (a god, an angel) can fight (D-69). | "Gods of living religions are above our pay grade. Try a god of myth, like Zeus, or a mythical creature, like a griffin." |
| **Groups of people** (nations, teams, bands) | Jokes are about the fighters, never about groups of people. | "We don't pit groups of people against each other. Pick an animal, a machine, or one fighter type like a Viking." |
| **Abstract ideas, places, landforms, planets** | They aren't physical fighters with measurable stats. | A message explaining what kinds of fighters work. |
| **More than two sides** | The arena only fits two sides for now. | It offers each pair as a two-sided matchup. Group a pack into one side, like "3 wolves". |
| **More than 10,000 on a side, or fractions** | It keeps the simulation fast and the fighters whole. | It lowers the count to 10,000 and says so on tonight's card, or asks how many whole fighters you meant. |
| **A group with no number, an odd number** ("a swarm of bees", "1e3 ants", "-3 lions") | The simulation needs a whole, positive count. | It reads the count for you and says so on tonight's card: a swarm or colony is 1,000, a school 100, a flock 30, a herd or troop 20, a pod or gaggle 10, a pack or pride 6; "1e3" is 1,000; "-3" is 3. A number you type always wins: "a pack of 12 wolves" and "a pack of about 12 wolves" are both 12 wolves. Two numbers are multiplied: "2 packs of 5 wolves" is 10 wolves, and the card says so. |

**What does work:** animals, historical fighter types (a Roman legionary, a medieval knight), military units (US Navy SEALs, who fight with a rifle), objects and weapons (a toaster, a sword, a grenade), plants, vehicles and machines (a bulldozer, a tank), gods of mythology (Zeus), and mythical creature types (a dragon, a griffin). Fighters off our list fight on labeled estimates. A mythical creature is modeled on the real animals its legends compare it to, and every one of its stats is tagged as an assumption.

The show is PG: knockouts and retreats, no blood or gore.

## 5. Troubleshooting

| Problem | Fix |
|---|---|
| **Windows: "running scripts is disabled on this system"** when you type `npm` | Type `npm.cmd` instead of `npm`, for example `npm.cmd run setup` and `npm.cmd start`. There's no need to change any Windows security settings. |
| **"'node' (or 'uv') is not recognized" / "command not found"** | Close the terminal and open a new one after installing, so it finds the new programs. If it still fails, install that program again (step 1). |
| **The page says "We couldn't reach the studio"**, or the browser says it can't connect to localhost:8000 | The app isn't running. Check that the `npm start` window is still open and shows "Application startup complete". If you closed it, run `npm start` again, then refresh the page (F5, or Cmd+R on Mac). |
| **"This fight was called off"** with "We don't have a stat sheet for …" | The app couldn't place that fighter. Pick one of the 15 fighters listed in [Type a matchup](#type-a-matchup), a mythical creature such as "a griffin", or click an example matchup. |
| **"Address already in use"** or port 8000 is busy when you run `npm start` | The app (or something else) is already running. Use the window where it's already running, or close it with Ctrl+C and run `npm start` again. Restarting the computer also clears it. |
| **The page looks old or a button does nothing after you update the code** | Stop the app with Ctrl+C, run `npm run setup` and then `npm start` again, and refresh the browser page. |
| **No announcer voice** | Sound is optional, and the captions always carry the show. Check that the button says **Sound on** (click it if it says **Sound off**) and your computer isn't muted. A note at the top of the broadcast says when the voice couldn't be made this time. |
| **`npm run setup` ends with "Not a git checkout (a ZIP copy?), so the commit guard was skipped"** | You downloaded the ZIP instead of cloning. That's normal: setup finished, so go on to the next step. |
| **"The knowledge base is empty, so new fighters can't be researched yet"** when you start the app | You're in live mode and the prebuilt knowledge base didn't load (the message just above says why, usually a different embedding model). Stop the app with Ctrl+C, run `npm run ingest` once ([step 5](#step-5-optional-refresh-the-knowledge-base)), then `npm start` again. |
| **"We have no stat sheet for '…', so its stats are estimates"** on the broadcast | Usually this just means that fighter isn't on the fighter list, so its stats are estimates, which is expected. If it names a listed fighter (for example a grizzly bear), the knowledge base is missing: see [step 5](#step-5-optional-refresh-the-knowledge-base). |
| **Everything looks like sample data** | You're in mock mode, which is fine for trying the app. To use the real AI endpoints, do [step 3](#step-3-connect-the-course-ai-endpoints-optional), then restart the app; it loads the prebuilt knowledge base on its first live start. |

Still stuck? Run `npm run env:check`. It checks your settings file and says what to fix, without showing any secret values.
