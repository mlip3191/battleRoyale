// Test helper: a tiny stand-in for the parts of Phaser the battle scene uses (jsdom has no canvas).
// It records games, tweens, and shakes so tests can check what the scene asked Phaser to do.
import { vi } from "vitest";

// A game object whose setters change real fields and return itself, like Phaser's.
export class FakeObject {
  x: number;
  y: number;
  alpha = 1;
  angle = 0;
  text: string;
  destroyed = false;
  constructor(x = 0, y = 0, text = "") {
    this.x = x;
    this.y = y;
    this.text = text;
  }
  setAlpha(a: number) {
    this.alpha = a;
    return this;
  }
  setX(x: number) {
    this.x = x;
    return this;
  }
  setPosition(x: number, y: number) {
    this.x = x;
    this.y = y;
    return this;
  }
  setText(text: string) {
    this.text = text;
    return this;
  }
  setDisplaySize() {
    return this;
  }
  setFlipX() {
    return this;
  }
  setOrigin() {
    return this;
  }
  setDepth() {
    return this;
  }
  setScale() {
    return this;
  }
  destroy() {
    this.destroyed = true;
  }
}

// Every Phaser game created while a test runs.
export const games: FakeGame[] = [];

export class FakeGame {
  config: { scene: unknown[] } & Record<string, unknown>;
  destroy = vi.fn();
  constructor(config: { scene: unknown[] } & Record<string, unknown>) {
    this.config = config;
    games.push(this);
  }
}

// The scene base class: just enough of add/make/textures/tweens/cameras for the battle scene.
export class FakeScene {
  textureKeys = new Set<string>();
  images: FakeObject[] = [];
  texts: FakeObject[] = [];
  load = { image: vi.fn() };
  tweens = { add: vi.fn(), killAll: vi.fn() };
  cameras = { main: { shake: vi.fn() } };
  time = { delayedCall: vi.fn() };
  textures = {
    exists: (key: string) => this.textureKeys.has(key),
    addDynamicTexture: (key: string) => {
      this.textureKeys.add(key);
      return { draw: vi.fn() };
    },
  };
  add = {
    image: (x: number, y: number, key: string) => {
      const image = new FakeObject(x, y, key);
      this.images.push(image);
      return image;
    },
    text: (x: number, y: number, text: string) => {
      const label = new FakeObject(x, y, text);
      this.texts.push(label);
      return label;
    },
    rectangle: (x: number, y: number) => new FakeObject(x, y),
  };
  make = {
    graphics: () => ({
      fillStyle: vi.fn(),
      fillCircle: vi.fn(),
      fillRoundedRect: vi.fn(),
      lineStyle: vi.fn(),
      strokeRoundedRect: vi.fn(),
      generateTexture: (key: string) => this.textureKeys.add(key),
      destroy: vi.fn(),
    }),
    text: (config: { text: string }) => new FakeObject(0, 0, config.text),
  };
  config: unknown;
  constructor(config?: unknown) {
    this.config = config;
  }
}

export const fakePhaser = {
  AUTO: 0,
  Scale: { FIT: 3, CENTER_HORIZONTALLY: 2 },
  Game: FakeGame,
  Scene: FakeScene,
};
