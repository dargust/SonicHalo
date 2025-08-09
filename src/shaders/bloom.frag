#version 330
uniform sampler2D texture0;
in vec2 uv;
out vec4 fragColor;

void main() {
    float brightness = dot(texture(texture0, uv).rgb, vec3(0.2126, 0.7152, 0.0722));
    if (brightness > 0.5) {
        fragColor = texture(texture0, uv) * 1.5; // glow up bright areas
    } else {
        fragColor = texture(texture0, uv) * 0.7;
    }
}
