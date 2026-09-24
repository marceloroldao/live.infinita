shader_type canvas_item;
render_mode unshaded;
uniform float night_amount : hint_range(0.0, 1.0) = 0.0;
uniform float dusk_amount : hint_range(0.0, 1.0) = 0.0;
void fragment() {
    vec3 top = mix(vec3(0.25, 0.55, 0.68), vec3(0.025, 0.055, 0.13), night_amount);
    vec3 bottom = mix(vec3(0.88, 0.89, 0.72), vec3(0.19, 0.27, 0.37), night_amount);
    bottom = mix(bottom, vec3(0.92, 0.53, 0.35), dusk_amount * 0.65);
    vec3 sky = mix(top, bottom, smoothstep(0.0, 0.64, UV.y));
    // Static sub-LSB dither avoids quantization bands and temporal noise.
    float dither = fract(sin(dot(FRAGCOORD.xy, vec2(12.9898, 78.233))) * 43758.5453);
    COLOR = vec4(sky + (dither - 0.5) / 255.0, 1.0);
}
