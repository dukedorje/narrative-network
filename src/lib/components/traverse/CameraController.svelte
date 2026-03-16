<script lang="ts">
	import { T, useTask } from '@threlte/core';
	import { OrbitControls } from '@threlte/extras';
	import { createSpring3D, setSpring3DTarget, tickSpring3D } from '../graph/spring';

	interface Props {
		/** World-space position to focus on. */
		focusPosition: { x: number; y: number; z: number } | null;
		/** 'overview' = pulled back, 'focus' = close to node. */
		mode: 'overview' | 'focus';
	}

	let { focusPosition = null, mode = 'overview' }: Props = $props();

	// Camera offset from focus target
	const OVERVIEW_OFFSET = { x: 0, y: 12, z: 20 };
	const FOCUS_OFFSET = { x: 0, y: 5, z: 10 };

	// Spring-animated camera position and lookAt target
	const cameraSpring = createSpring3D(
		OVERVIEW_OFFSET.x,
		OVERVIEW_OFFSET.y,
		OVERVIEW_OFFSET.z
	);
	const lookAtSpring = createSpring3D(0, 0, 0);

	let cameraPos = $state({ x: OVERVIEW_OFFSET.x, y: OVERVIEW_OFFSET.y, z: OVERVIEW_OFFSET.z });
	let lookAtPos = $state({ x: 0, y: 0, z: 0 });
	let isAnimating = $state(false);

	// OrbitControls ref — updated imperatively only
	let controls: any = $state(null);

	// When focus changes, update spring targets
	$effect(() => {
		const offset = mode === 'focus' ? FOCUS_OFFSET : OVERVIEW_OFFSET;
		const target = focusPosition ?? { x: 0, y: 0, z: 0 };

		setSpring3DTarget(
			cameraSpring,
			target.x + offset.x,
			target.y + offset.y,
			target.z + offset.z
		);
		setSpring3DTarget(lookAtSpring, target.x, target.y, target.z);
		isAnimating = true;
	});

	// Tick springs on Threlte's render loop — no private RAF
	useTask((delta) => {
		if (!isAnimating) return;

		const dt = Math.min(delta, 0.05);

		const camMoving = tickSpring3D(cameraSpring, dt, 0.12, 0.001);
		const lookMoving = tickSpring3D(lookAtSpring, dt, 0.1, 0.001);

		cameraPos = {
			x: cameraSpring.x.value,
			y: cameraSpring.y.value,
			z: cameraSpring.z.value
		};
		lookAtPos = {
			x: lookAtSpring.x.value,
			y: lookAtSpring.y.value,
			z: lookAtSpring.z.value
		};

		// Update OrbitControls target imperatively (single source of truth)
		if (controls) {
			controls.target.set(lookAtPos.x, lookAtPos.y, lookAtPos.z);
			controls.update();
		}

		if (!camMoving && !lookMoving) {
			isAnimating = false;
		}
	});
</script>

<T.PerspectiveCamera
	makeDefault
	position={[cameraPos.x, cameraPos.y, cameraPos.z]}
	fov={55}
	near={0.1}
	far={200}
>
	<OrbitControls
		bind:ref={controls}
		enableDamping
		dampingFactor={0.08}
		minDistance={3}
		maxDistance={60}
		maxPolarAngle={Math.PI * 0.85}
	/>
</T.PerspectiveCamera>
