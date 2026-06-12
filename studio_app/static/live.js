function initLive() {
  console.log('live stub');
  const parts = window.location.pathname.split('/').filter(Boolean);
  if (parts[0] === 'live') {
    const bookIds = parts.slice(1).map(Number).filter((n) => !Number.isNaN(n));
    console.log('book ids:', bookIds);
  }
}
