import { writable } from 'svelte/store';
import { browser } from '$app/environment';

export const audioEnabled = writable(false);
export const ambientVolume = writable(0.4);
export const uiVolume = writable(0.8);

class AudioManager {
	private uiSounds: Record<string, HTMLAudioElement> = {};
	private ambientPlayer: HTMLAudioElement | null = null;
	private initialized = false;

	init() {
		if (!browser || this.initialized) return;

		this.uiSounds = {
			hover: new Audio('/sounds/fx/zap-sound-06-474813.mp3'),
			click: new Audio('/sounds/fx/mixkit-retro-video-game-bubble-laser-277.wav'),
			success: new Audio('/sounds/fx/bonus-alert-767.wav')
		};

		// Preload and set volume
		Object.values(this.uiSounds).forEach(audio => {
			audio.load();
			// Listen to volume store changes
			uiVolume.subscribe(vol => {
				audio.volume = vol;
			});
		});

		this.ambientPlayer = new Audio('/sounds/env/ambient-251.mp3');
		this.ambientPlayer.loop = true;
		
		ambientVolume.subscribe(vol => {
			if (this.ambientPlayer) this.ambientPlayer.volume = vol;
		});

		// Listen to enable/disable toggle
		audioEnabled.subscribe(enabled => {
			if (enabled) {
				this.ambientPlayer?.play().catch(() => {
					// Audio might be blocked by browser policy until interaction
					console.warn('Ambient playback prevented by browser');
				});
			} else {
				this.ambientPlayer?.pause();
			}
		});

		this.initialized = true;
	}

	playUiSound(name: 'hover' | 'click' | 'success') {
		if (!browser || !this.initialized) return;
		
		let isEnabled = false;
		audioEnabled.subscribe(v => isEnabled = v)();
		
		if (isEnabled && this.uiSounds[name]) {
			// Clone node to allow rapid overlapping sounds
			const sound = this.uiSounds[name].cloneNode() as HTMLAudioElement;
			let vol = 0.5;
			uiVolume.subscribe(v => vol = v)();
			// Zap sound is super loud, scale it back
			sound.volume = name === 'hover' ? vol * 0.1 : vol * 0.3;
			sound.play().catch(e => console.warn('UI sound failed:', e));
		}
	}
}

export const audioManager = new AudioManager();
