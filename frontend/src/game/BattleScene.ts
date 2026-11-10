// The Phaser scene that replays a fight (D05). It only plays the timeline's beats; it never decides
// an outcome. Phaser is passed in (createBattleScene) so this file never imports it at runtime and
// Phaser stays in its own lazily loaded chunk.
import type Phaser from "phaser";
import type { SimulationResult } from "../api/client.ts";
import {
  MAX_SPRITES_PER_SIDE,
  STAGE,
  badgeText,
  visibleSlots,
  type SideLayout,
} from "./layout.ts";
import {
  ReplayClock,
  keyFrames,
  type Beat,
  type Side,
  type Speed,
  type Timeline,
} from "./timeline.ts";

export interface BattleSceneOptions {
  timeline: Timeline;
  layouts: [SideLayout, SideLayout];
  battlefieldUrl: string | null;
  outcome: SimulationResult["outcome"];
  reducedMotion: boolean;
  onEvent: (index: number) => void; // every event index, once, in order
  onFinish: () => void; // the last event was reached
}

// What React can call on the scene (the controls) and what tests drive.
export interface BattleStage {
  readonly clock: ReplayClock;
  play(): void;
  pause(): void;
  setSpeed(speed: Speed): void;
  skipToEnd(): void;
  update(time: number, delta: number): void;
}

export const SCENE_KEY = "battle";
const MAX_FRAME_MS = 100; // a long pause (hidden tab) never jumps more than this per frame
const BATTLEFIELD_KEY = "battlefield";
const CROWD_KEY = "crowd-icon";
const APPROACH_PX = 120; // how far each squad walks in when it closes in
const TEXT_FONT = "Arial Black, Impact, sans-serif";

// One side on stage: its sprites, where they stand, and how many are still in the fight.
interface Squad {
  layout: SideLayout;
  sprites: Phaser.GameObjects.Image[];
  home: { x: number; y: number }[];
  down: boolean[];
  alive: number;
  gone: boolean;
  badge: Phaser.GameObjects.Text | null;
}

// Build the scene class on top of the Phaser namespace that was loaded at runtime.
export function createBattleScene(P: typeof Phaser) {
  return class BattleScene extends P.Scene implements BattleStage {
    readonly clock: ReplayClock;
    private readonly opts: BattleSceneOptions;
    private readonly keys: Set<number>; // beat indexes shown in reduced motion
    private squads: [Squad, Squad] | null = null; // set once create() has built the stage
    private pending: Beat[] = []; // reduced motion: changes waiting for the next key frame

    constructor(opts: BattleSceneOptions) {
      super({ key: SCENE_KEY });
      this.opts = opts;
      this.clock = new ReplayClock(opts.timeline);
      this.keys = new Set(keyFrames(opts.timeline.beats).map((b) => b.index));
    }

    // Queue the battle's images; anything that fails to load falls back to a placeholder.
    preload() {
      const { layouts, battlefieldUrl } = this.opts;
      for (const side of layouts) {
        if (side.spriteUrl) this.load.image(side.textureKey, side.spriteUrl);
      }
      if (battlefieldUrl) this.load.image(BATTLEFIELD_KEY, battlefieldUrl);
    }

    // Draw the backdrop and both squads at their starting spots.
    create() {
      this.drawBackdrop();
      this.makeCrowdIcon();
      this.squads = [this.buildSquad(0), this.buildSquad(1)];
      if (this.opts.reducedMotion) this.showKeyFrameNote();
    }

    play() {
      this.clock.play();
    }

    pause() {
      this.clock.pause();
    }

    setSpeed(speed: Speed) {
      this.clock.setSpeed(speed);
    }

    // Jump to the end: report every remaining event, then show the final state with no animation.
    skipToEnd() {
      const reached = this.clock.skipToEnd();
      if (this.squads) {
        this.tweens.killAll();
        this.snapHome();
      }
      for (const index of reached) {
        this.opts.onEvent(index);
        this.apply(this.clock.beats[index], true);
      }
      this.opts.onFinish();
    }

    // Phaser calls this every frame: move the clock and play whatever beats it reached.
    update(_time: number, delta: number) {
      if (!this.clock.playing) return;
      const reached = this.clock.advance(Math.min(delta, MAX_FRAME_MS));
      for (const index of reached) {
        this.opts.onEvent(index);
        this.playBeat(this.clock.beats[index]);
      }
      if (reached.length > 0 && this.clock.done) this.opts.onFinish();
    }

    // Animate one beat (or, in reduced motion, hold it until the next key frame).
    private playBeat(beat: Beat) {
      if (!this.squads) return;
      if (!this.opts.reducedMotion) {
        this.apply(beat, false);
        return;
      }
      this.pending.push(beat);
      if (!this.keys.has(beat.index)) return;
      for (const held of this.pending) this.apply(held, true);
      this.pending = [];
    }

    // Show what a beat changes; `instant` skips every tween, shake, and floating text.
    private apply(beat: Beat, instant: boolean) {
      if (!this.squads) return;
      const ms = beat.duration / this.clock.speed;
      switch (beat.kind) {
        case "approach":
          if (beat.actorSide !== null)
            this.approach(beat.actorSide, ms, instant);
          break;
        case "lunge":
        case "hit":
        case "miss":
          if (!instant) this.strike(beat, ms);
          break;
        case "ko":
        case "crowd-ko":
          if (beat.affectedSide !== null) this.knockOut(beat, ms, instant);
          break;
        case "retreat":
        case "flee":
          if (beat.actorSide !== null) this.run(beat, ms, instant);
          break;
        case "stalemate":
          this.banner("STALEMATE", ms, instant, false);
          break;
        case "end":
          this.banner(this.endText(beat), ms, instant, true);
          break;
      }
    }

    private drawBackdrop() {
      const { width, height } = STAGE;
      if (this.textures.exists(BATTLEFIELD_KEY)) {
        this.add
          .image(width / 2, height / 2, BATTLEFIELD_KEY)
          .setDisplaySize(width, height)
          .setAlpha(0.85);
        return;
      }
      this.add.rectangle(width / 2, height / 2, width, height, 0x0b1026);
      this.add.rectangle(width / 2, height - 50, width, 100, 0x161d42);
      this.add.rectangle(width / 2, height - 100, width, 3, 0x3ee6ff);
    }

    // A little three-head crowd marker for group events, drawn in code.
    private makeCrowdIcon() {
      if (this.textures.exists(CROWD_KEY)) return;
      const g = this.make.graphics({ x: 0, y: 0 }, false);
      g.fillStyle(0xffd23f, 1);
      for (const [x, y] of [
        [8, 10],
        [24, 6],
        [40, 10],
      ]) {
        g.fillCircle(x, y, 6);
        g.fillRoundedRect(x - 7, y + 7, 14, 14, 4);
      }
      g.generateTexture(CROWD_KEY, 48, 28);
      g.destroy();
    }

    // The side's sprite texture: the loaded image, or a placeholder shape with the initial.
    private textureFor(layout: SideLayout) {
      if (this.textures.exists(layout.textureKey)) return layout.textureKey;
      const key = `placeholder-${layout.side}`;
      if (this.textures.exists(key)) return key;
      const size = 128;
      const color =
        layout.placeholder?.color ?? (layout.side === 0 ? 0x2f6bff : 0xe5384f);
      const initial =
        layout.placeholder?.initial ??
        (layout.name.charAt(0).toUpperCase() || "?");
      const g = this.make.graphics({ x: 0, y: 0 }, false);
      g.fillStyle(color, 1);
      g.fillRoundedRect(4, 4, size - 8, size - 8, 28);
      g.lineStyle(6, 0xffffff, 0.9);
      g.strokeRoundedRect(4, 4, size - 8, size - 8, 28);
      const label = this.make
        .text(
          {
            x: 0,
            y: 0,
            text: initial,
            style: {
              fontFamily: TEXT_FONT,
              fontSize: "72px",
              color: "#ffffff",
            },
          },
          false,
        )
        .setOrigin(0.5);
      const texture = this.textures.addDynamicTexture(key, size, size);
      texture?.draw(g, 0, 0);
      texture?.draw(label, size / 2, size / 2);
      g.destroy();
      label.destroy();
      return key;
    }

    private buildSquad(side: Side): Squad {
      const layout = this.opts.layouts[side];
      const key = this.textureFor(layout);
      // Side 1 faces left, but a placeholder is never mirrored (its initial would read backwards).
      const sprites = layout.slots.map(({ x, y }) =>
        this.add
          .image(x, y, key)
          .setDisplaySize(layout.size, layout.size)
          .setFlipX(side === 1 && key === layout.textureKey),
      );
      const nameX = side === 0 ? 24 : STAGE.width - 24;
      this.add
        .text(nameX, 20, layout.name.toUpperCase(), {
          fontFamily: TEXT_FONT,
          fontSize: "22px",
          color: side === 0 ? "#9ec0ff" : "#ffb3bd",
        })
        .setOrigin(side === 0 ? 0 : 1, 0);
      const badge = layout.badge
        ? this.add
            .text(nameX, 52, layout.badge, {
              fontFamily: TEXT_FONT,
              fontSize: "20px",
              color: "#0b1026",
              backgroundColor: "#ffd23f",
              padding: { x: 8, y: 2 },
            })
            .setOrigin(side === 0 ? 0 : 1, 0)
        : null;
      return {
        layout,
        sprites,
        home: layout.slots.map((s) => ({ ...s })),
        down: sprites.map(() => false),
        alive: layout.count,
        gone: false,
        badge,
      };
    }

    // Both squads close part of the gap; there are no positions in the log, so the scene picks them.
    private approach(side: Side, ms: number, instant: boolean) {
      const squad = this.squads![side];
      const step = side === 0 ? 1 : -1;
      squad.home.forEach((spot, i) => {
        spot.x += step * APPROACH_PX;
        this.moveTo(squad.sprites[i], spot.x, ms, instant);
      });
    }

    // Lunge toward the other side; a hit adds a small shake and floating damage, a miss a whiff.
    private strike(beat: Beat, ms: number) {
      if (beat.actorSide === null || beat.affectedSide === null) return;
      const attackers = this.pick(
        beat.actorSide,
        beat.group ? Math.min(beat.count, 5) : 1,
        beat.actor,
      );
      const step = beat.actorSide === 0 ? 1 : -1;
      for (const sprite of attackers) {
        this.tweens.add({
          targets: sprite,
          x: sprite.x + step * 36,
          duration: Math.max(60, ms * 0.35),
          yoyo: true,
          ease: "Quad.easeOut",
        });
      }
      const at = this.focus(beat.affectedSide, beat.group ? null : beat.target);
      if (beat.group) this.crowdMarker(beat.actorSide, beat.count, ms);
      if (beat.kind === "hit") {
        this.cameras.main.shake(Math.min(160, ms * 0.4), 0.004);
        if (beat.damage !== null)
          this.floatText(
            at.x,
            at.y,
            `-${formatDamage(beat.damage)}`,
            "#ff6fb5",
            ms,
          );
      } else if (beat.kind === "miss") {
        this.floatText(at.x, at.y, "whiff!", "#b8c1e8", ms);
      }
    }

    // Fallen fighters fade out; a crowd loses sprites in proportion and its badge counts down.
    private knockOut(beat: Beat, ms: number, instant: boolean) {
      const side = beat.affectedSide!;
      const squad = this.squads![side];
      const fell = Math.max(1, beat.count);
      squad.alive = Math.max(0, squad.alive - fell);
      const fits = squad.layout.count <= squad.sprites.length;
      if (
        fits &&
        beat.target !== null &&
        squad.sprites[beat.target] &&
        !squad.down[beat.target]
      ) {
        this.fall(squad, beat.target, ms, instant);
      }
      const keep = visibleSlots(
        squad.alive,
        squad.layout.count,
        squad.sprites.length,
      );
      for (
        let i = squad.sprites.length - 1;
        i >= 0 && this.standing(squad) > keep;
        i -= 1
      ) {
        if (!squad.down[i]) this.fall(squad, i, ms, instant);
      }
      if (squad.badge && squad.layout.count > MAX_SPRITES_PER_SIDE)
        squad.badge.setText(badgeText(squad.alive));
      if (beat.group && !instant) this.crowdMarker(side, fell, ms, true);
    }

    // Retreat backs the squad toward its own edge; flee runs it off-screen.
    private run(beat: Beat, ms: number, instant: boolean) {
      const side = beat.actorSide!;
      const squad = this.squads![side];
      const away = side === 0 ? -1 : 1;
      squad.home.forEach((spot, i) => {
        spot.x =
          beat.kind === "flee"
            ? side === 0
              ? -80
              : STAGE.width + 80
            : spot.x + away * 90;
        this.moveTo(squad.sprites[i], spot.x, ms, instant);
      });
      if (beat.kind === "flee") squad.gone = true;
    }

    private endText(beat: Beat) {
      if (beat.winner !== null)
        return `${this.opts.layouts[beat.winner].name.toUpperCase()} WINS!`;
      return this.opts.outcome === "no_contest" ? "NO CONTEST" : "IT'S A DRAW!";
    }

    // A gold lower-third banner across the stage; the end banner stays up.
    private banner(text: string, ms: number, instant: boolean, stay: boolean) {
      const y = STAGE.height / 2;
      const box = this.add
        .rectangle(STAGE.width / 2, y, STAGE.width * 0.8, 84, 0xffd23f)
        .setDepth(10);
      const label = this.add
        .text(STAGE.width / 2, y, text, {
          fontFamily: TEXT_FONT,
          fontSize: "40px",
          color: "#0b1026",
        })
        .setOrigin(0.5)
        .setDepth(11);
      if (instant) {
        if (!stay)
          this.time.delayedCall(Math.max(400, ms), () =>
            [box, label].forEach((o) => o.destroy()),
          );
        return;
      }
      box.setScale(0, 1);
      this.tweens.add({
        targets: box,
        scaleX: 1,
        duration: Math.min(300, ms / 2),
        ease: "Back.easeOut",
      });
      if (!stay) {
        this.tweens.add({
          targets: [box, label],
          alpha: 0,
          delay: ms * 0.7,
          duration: ms * 0.3,
          onComplete: () => [box, label].forEach((o) => o.destroy()),
        });
      }
    }

    private showKeyFrameNote() {
      this.add
        .text(
          STAGE.width / 2,
          STAGE.height - 24,
          "Reduced motion: key moments only",
          {
            fontFamily: TEXT_FONT,
            fontSize: "16px",
            color: "#b8c1e8",
          },
        )
        .setOrigin(0.5);
    }

    // Up to `n` standing sprites of a side: the named fighter if it has its own sprite, else the front ones.
    private pick(side: Side, n: number, index: number | null) {
      const squad = this.squads![side];
      const standing = squad.sprites.filter((_, i) => !squad.down[i]);
      if (
        index !== null &&
        squad.layout.count <= squad.sprites.length &&
        !squad.down[index] &&
        squad.sprites[index]
      ) {
        return [squad.sprites[index]];
      }
      return standing.slice(0, n);
    }

    // Where to show a floating number: the targeted fighter, or the middle of the side's crowd.
    private focus(side: Side, index: number | null) {
      const squad = this.squads![side];
      const one =
        index !== null && squad.layout.count <= squad.sprites.length
          ? squad.sprites[index]
          : undefined;
      if (one && !squad.down[index!])
        return { x: one.x, y: one.y - squad.layout.size / 2 };
      const standing = squad.sprites.filter((_, i) => !squad.down[i]);
      const list = standing.length > 0 ? standing : squad.sprites;
      const x = list.reduce((sum, s) => sum + s.x, 0) / list.length;
      const y = list.reduce((sum, s) => sum + s.y, 0) / list.length;
      return { x, y: y - 40 };
    }

    private standing(squad: Squad) {
      return squad.down.filter((d) => !d).length;
    }

    private fall(squad: Squad, i: number, ms: number, instant: boolean) {
      squad.down[i] = true;
      const sprite = squad.sprites[i];
      if (instant) {
        sprite.setAlpha(0);
        return;
      }
      this.tweens.add({
        targets: sprite,
        alpha: 0,
        angle: squad.layout.side === 0 ? -80 : 80,
        y: sprite.y + 12,
        duration: Math.max(120, ms * 0.8),
      });
    }

    private moveTo(
      sprite: Phaser.GameObjects.Image,
      x: number,
      ms: number,
      instant: boolean,
    ) {
      if (instant) {
        sprite.setX(x);
        return;
      }
      this.tweens.add({
        targets: sprite,
        x,
        duration: Math.max(120, ms * 0.9),
        ease: "Sine.easeInOut",
      });
    }

    // After a skip, put every sprite back on its spot (killed tweens can leave one mid-lunge).
    private snapHome() {
      for (const squad of this.squads!) {
        squad.sprites.forEach((sprite, i) =>
          sprite.setPosition(squad.home[i].x, squad.home[i].y),
        );
      }
    }

    private floatText(
      x: number,
      y: number,
      text: string,
      color: string,
      ms: number,
    ) {
      const label = this.add
        .text(x, y, text, {
          fontFamily: TEXT_FONT,
          fontSize: "26px",
          color,
          stroke: "#0b1026",
          strokeThickness: 5,
        })
        .setOrigin(0.5)
        .setDepth(5);
      this.tweens.add({
        targets: label,
        y: y - 50,
        alpha: 0,
        duration: Math.max(250, ms),
        onComplete: () => label.destroy(),
      });
    }

    // A crowd icon with "× N" over the side whose group acted or fell.
    private crowdMarker(side: Side, count: number, ms: number, fell = false) {
      const at = this.focus(side, null);
      const icon = this.add
        .image(at.x - 22, at.y - 30, CROWD_KEY)
        .setDepth(6)
        .setAlpha(fell ? 0.6 : 1);
      const label = this.add
        .text(at.x + 8, at.y - 30, badgeText(count), {
          fontFamily: TEXT_FONT,
          fontSize: "18px",
          color: "#ffd23f",
          stroke: "#0b1026",
          strokeThickness: 4,
        })
        .setOrigin(0, 0.5)
        .setDepth(6);
      this.tweens.add({
        targets: [icon, label],
        y: "-=24",
        alpha: 0,
        duration: Math.max(250, ms),
        onComplete: () => [icon, label].forEach((o) => o.destroy()),
      });
    }
  };
}

// Damage is shown exactly as the log has it, trimmed to one decimal place.
const formatDamage = (damage: number) =>
  damage.toLocaleString("en-US", { maximumFractionDigits: 1 });
