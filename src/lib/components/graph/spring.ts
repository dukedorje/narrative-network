/**
 * Critically-damped spring for smooth animations.
 * Used for camera fly-to, node scale/color transitions, etc.
 *
 * Based on the exact solution to: x'' + 2ζω·x' + ω²·x = ω²·target
 * where ζ = 1 (critically damped), ω = 2π / halfLife
 */

export interface SpringState {
	value: number;
	velocity: number;
	target: number;
}

export interface Spring3D {
	x: SpringState;
	y: SpringState;
	z: SpringState;
}

const TWO_PI = Math.PI * 2;

/**
 * Advance a 1D critically-damped spring by `dt` seconds.
 * halfLife: time (seconds) for the spring to reach ~50% of remaining distance.
 * Returns true if still moving (|delta| > epsilon).
 */
export function tickSpring(s: SpringState, dt: number, halfLife = 0.15, epsilon = 0.0001): boolean {
	const omega = TWO_PI / (halfLife * 2); // natural frequency
	const exp = Math.exp(-omega * dt);
	const delta = s.value - s.target;
	const newValue = s.target + (delta + (s.velocity + omega * delta) * dt) * exp;
	const newVelocity = (s.velocity - (s.velocity + omega * delta) * omega * dt) * exp;

	s.value = newValue;
	s.velocity = newVelocity;

	return Math.abs(newValue - s.target) > epsilon || Math.abs(newVelocity) > epsilon;
}

/** Create a spring initialized at rest at `value`. */
export function createSpring(value: number, target?: number): SpringState {
	return { value, velocity: 0, target: target ?? value };
}

/** Create a 3D spring (three independent axes). */
export function createSpring3D(x: number, y: number, z: number): Spring3D {
	return {
		x: createSpring(x),
		y: createSpring(y),
		z: createSpring(z)
	};
}

/** Set target for a 3D spring. */
export function setSpring3DTarget(s: Spring3D, x: number, y: number, z: number) {
	s.x.target = x;
	s.y.target = y;
	s.z.target = z;
}

/** Tick all three axes. Returns true if any axis is still moving. */
export function tickSpring3D(s: Spring3D, dt: number, halfLife = 0.15, epsilon = 0.0001): boolean {
	const ax = tickSpring(s.x, dt, halfLife, epsilon);
	const ay = tickSpring(s.y, dt, halfLife, epsilon);
	const az = tickSpring(s.z, dt, halfLife, epsilon);
	return ax || ay || az;
}

/** Snap a 3D spring to its target instantly. */
export function snapSpring3D(s: Spring3D) {
	s.x.value = s.x.target;
	s.x.velocity = 0;
	s.y.value = s.y.target;
	s.y.velocity = 0;
	s.z.value = s.z.target;
	s.z.velocity = 0;
}
