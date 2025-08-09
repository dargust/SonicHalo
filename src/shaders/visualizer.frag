#version 330

uniform float amps[32];
uniform float time; // time in seconds, passed in by the host
in vec2 uv;
out vec4 fragColor;

void main() {
    // Center UV [-1, 1]
    vec2 centerUV = uv * 2.0 - 1.0;

    // Rotate coordinates over time
    float rotationSpeed = 0.5; // radians per second
    float angleOffset = time * rotationSpeed;

    float cosA = cos(angleOffset);
    float sinA = sin(angleOffset);
    vec2 rotatedUV = vec2(
        centerUV.x * cosA - centerUV.y * sinA,
        centerUV.x * sinA + centerUV.y * cosA
    );

    float dist = length(rotatedUV);
    float angle = atan(rotatedUV.y, rotatedUV.x); // [-π, π]

    // Normalize angle to [0, 1], map to bar index
    float normalizedAngle = (angle + 3.1415926) / (2.0 * 3.1415926);
    int i = int(normalizedAngle * 32.0);
    i = clamp(i, 0, 31);

    float amp = amps[i];

    // Ring shape
    float baseRadius = 0.4;
    float barLength = amp * 0.3 + 0.02;

    // Smooth edges
    float edgeSmooth = 0.01;
    float inside = smoothstep(baseRadius, baseRadius + edgeSmooth, dist);
    float outside = smoothstep(baseRadius + barLength, baseRadius + barLength - edgeSmooth, dist);
    float barMask = inside * outside;

    // Color from green (low) to red (high)
    vec3 color = mix(vec3(0.0, 1.0, 0.0), vec3(1.0, 0.0, 0.0), amp);

    fragColor = vec4(color * barMask, barMask);
}
