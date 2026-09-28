shader_type canvas_item;
render_mode unshaded;

// Native-only CPU rasterizer variant: same palette, gradient and sub-LSB dither
// amplitude as story_sky.gdshader, but no per-fragment trigonometry.
uniform float night_amount : hint_range(0.0, 1.0) = 0.0;
uniform float dusk_amount : hint_range(0.0, 1.0) = 0.0;

void fragment() {
    vec3 top = mix(vec3(0.25, 0.55, 0.68), vec3(0.025, 0.055, 0.13), night_amount);
    vec3 bottom = mix(vec3(0.88, 0.89, 0.72), vec3(0.19, 0.27, 0.37), night_amount);
    bottom = mix(bottom, vec3(0.92, 0.53, 0.35), dusk_amount * 0.65);
    vec3 sky = mix(top, bottom, smoothstep(0.0, 0.64, UV.y));

    // Stable 4x4 screen-space dither. The maximum difference to the legacy
    // shader is less than 1/255 per color channel, preserving the sky gradient.
    vec2 pixel_cell = mod(floor(FRAGCOORD.xy), 4.0);
    float dither = fract(dot(pixel_cell, vec2(0.75487766, 0.56984029)));
    COLOR = vec4(sky + (dither - 0.5) / 255.0, 1.0);
}
