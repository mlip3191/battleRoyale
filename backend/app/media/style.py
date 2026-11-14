"""The image "style lock" (A08): one place for every setting that makes sprites look like a set.

Every sprite request uses the same template, seed, size, negative prompt, and background edit
prompt; every battlefield uses its own template with the same seed and negative prompt. Change
any of these and bump STYLE_VERSION, so cached files drawn in the old style are not reused.

num_inference_steps and guidance_scale are not sent: the server's defaults gave good sprites in
the hand test, and there was no reason to pin other values. If the server's defaults ever change,
pin them here (and bump STYLE_VERSION).
"""

STYLE_VERSION = "v1"
SEED = 1234
SPRITE_SIZE = (512, 512)  # width, height; multiples of 16
BATTLEFIELD_SIZE = (768, 432)
NEGATIVE_PROMPT = "text, letters, watermark, logo, signature, frame, multiple characters"

# {article} is "a" or "an"; {subject} is the media_name plus plain-word lore phrases.
SPRITE_TEMPLATE = (
    "crude 16-bit side-view sprite of {article} {subject}, plain background, facing right, "
    "game asset"
)
# The model can't draw real transparency, so the edit paints a flat key colour that code removes.
BACKGROUND_EDIT_PROMPT = (
    "Replace the entire background with one flat solid pure magenta color (#FF00FF). "
    "Keep the sprite exactly the same. No checkerboard, no shadow, no border."
)
BATTLEFIELD_TEMPLATE = (
    "crude 16-bit side-view video game battle background of {scene}, wide landscape, "
    "empty scene, no characters, no animals, no text"
)


# "WIDTHxHEIGHT", the size format the image endpoint expects.
def size_text(size: tuple[int, int]) -> str:
    return f"{size[0]}x{size[1]}"
