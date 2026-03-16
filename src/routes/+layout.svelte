<script lang="ts">
	import '../app.css';
	import favicon from '$lib/assets/favicon.svg';
	import { page } from '$app/state';

	let { children } = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<title>Narrative Network — Knowledge Graph Explorer</title>
</svelte:head>

<div class="app">
	<header>
		<a href="/" class="logo">
			<span class="logo-icon">◈</span>
			<span class="logo-text">Narrative Network</span>
		</a>
		<nav>
			<a href="/" class="nav-link" class:active={page.url.pathname === '/'}>
				<span class="nav-icon">&#x25C7;</span>
				Explorer
			</a>
			<a href="/traverse" class="nav-link" class:active={page.url.pathname === '/traverse'}>
				<span class="nav-icon">&#x25C8;</span>
				Traverse
			</a>
		</nav>
	</header>

	<main>
		{@render children()}
	</main>
</div>

<style>
	.app {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		background: #020617;
		color: #e2e8f0;
	}

	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 16px 24px;
		border-bottom: 1px solid #1e293b;
		background: #0f172a;
	}

	.logo {
		display: flex;
		align-items: center;
		gap: 10px;
		text-decoration: none;
		color: #e2e8f0;
	}

	.logo-icon {
		font-size: 24px;
		color: #6ee7b7;
	}

	.logo-text {
		font-size: 18px;
		font-weight: 600;
		letter-spacing: -0.02em;
	}

	nav {
		display: flex;
		gap: 16px;
	}

	.nav-link {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 6px 16px;
		border: 1px solid #334155;
		border-radius: 8px;
		color: #94a3b8;
		text-decoration: none;
		font-size: 14px;
		transition: all 0.18s;
	}

	.nav-link:hover {
		color: #e2e8f0;
		border-color: #6ee7b7;
		background: rgba(110, 231, 183, 0.06);
	}

	.nav-link.active {
		color: #6ee7b7;
		border-color: #6ee7b7;
		background: rgba(110, 231, 183, 0.1);
	}

	.nav-icon {
		font-size: 14px;
		color: #6ee7b7;
	}

	main {
		flex: 1;
		display: flex;
		flex-direction: column;
	}
</style>
