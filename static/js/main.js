/**
 * FF TECH — Frontend Utilities
 */

// Format large numbers into human-readable strings (e.g., 1024 -> 1KB)
function formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

// Copy Audit URL to clipboard
function copyAuditLink(url) {
    navigator.clipboard.writeText(url).then(() => {
        alert("Audit link copied to clipboard!");
    });
}

// Helper to show/hide elements with a fade
function fadeToggle(elementId, show = true) {
    const el = document.getElementById(elementId);
    if (show) {
        el.style.display = 'block';
        el.classList.add('glass-entry');
    } else {
        el.style.display = 'none';
    }
}
