// Common utility functions shared across the application

/**
 * Calculate gradient color for score badges
 * Uses gray-blue-purple gradient:
 * - Gray (0.0): rgb(149, 165, 166)
 * - Blue (0.5): rgb(59, 130, 246)
 * - Purple (1.0): rgb(147, 51, 204)
 */
function getScoreGradientColor(score) {
    // Handle null/undefined scores
    if (score === null || score === undefined) {
        return 'rgb(149, 165, 166)'; // Gray for null scores
    }

    let r, g, b;

    if (score < 0.5) {
        // Gray to Blue transition (0.0 to 0.5)
        const t = score * 2;
        r = Math.round(149 + (59 - 149) * t);
        g = Math.round(165 + (130 - 165) * t);
        b = Math.round(166 + (246 - 166) * t);
    } else {
        // Blue to Purple transition (0.5 to 1.0)
        const t = (score - 0.5) * 2;
        r = Math.round(59 + (147 - 59) * t);
        g = Math.round(130 + (51 - 130) * t);
        b = Math.round(246 + (204 - 246) * t);
    }

    return `rgb(${r}, ${g}, ${b})`;
}

/**
 * Calculate gradient color for similarity badges
 * Uses gray-orange-red gradient:
 * - Gray (0.0): rgb(149, 165, 166)
 * - Orange (0.5): rgb(255, 165, 0)
 * - Red (1.0): rgb(220, 53, 69)
 */
function getSimilarityGradientColor(similarity) {
    // Handle null/undefined similarity
    if (similarity === null || similarity === undefined) {
        return 'rgb(149, 165, 166)'; // Gray for null similarity
    }

    let r, g, b;

    if (similarity < 0.5) {
        // Gray to Orange transition (0.0 to 0.5)
        const t = similarity * 2;
        r = Math.round(149 + (255 - 149) * t);
        g = Math.round(165 + (165 - 165) * t);
        b = Math.round(166 + (0 - 166) * t);
    } else {
        // Orange to Red transition (0.5 to 1.0)
        const t = (similarity - 0.5) * 2;
        r = Math.round(255 + (220 - 255) * t);
        g = Math.round(165 + (53 - 165) * t);
        b = Math.round(0 + (69 - 0) * t);
    }

    return `rgb(${r}, ${g}, ${b})`;
}

/**
 * Format date according to user's preference
 * @param {number|string} timestamp - Unix timestamp in seconds or date string
 * @param {string} format - Date format string (moment.js style)
 * @param {string} timezone - IANA timezone name
 * @returns {string} Formatted date string
 */
function formatDate(timestamp, format, timezone) {
    // Defaults
    format = format || window.userDateFormat || 'MMM D, YYYY';
    timezone = timezone || window.userTimezone || 'UTC';

    // Normalize to Date
    let date;
    if (typeof timestamp === 'number' || /^\d+$/.test(timestamp)) {
        date = new Date(parseInt(timestamp) * 1000);
    } else {
        date = new Date(timestamp);
    }
    if (isNaN(date.getTime())) return 'Invalid Date';

    // Use Intl to extract parts in the requested timezone
    const partsShortMonth = new Intl.DateTimeFormat('en-US', { timeZone: timezone, month: 'short' }).formatToParts(date);
    const partsNumeric = new Intl.DateTimeFormat('en-US', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(date);

    const getPart = (parts, type) => {
        const p = parts.find(x => x.type === type);
        return p ? p.value : '';
    };

    const year = getPart(partsNumeric, 'year');
    const month2 = getPart(partsNumeric, 'month');
    const day2 = getPart(partsNumeric, 'day');
    const monthShort = getPart(partsShortMonth, 'month');

    const month = String(parseInt(month2, 10));
    const day = String(parseInt(day2, 10));

    // Token replacement
    let formatted = String(format);
    formatted = formatted.replace('YYYY', year);
    formatted = formatted.replace('MMM', monthShort);
    formatted = formatted.replace('MM', month2);
    formatted = formatted.replace('M', month);
    formatted = formatted.replace('DD', day2);
    formatted = formatted.replace('D', day);
    return formatted;
}

/**
 * Format date and time according to user's preference
 * @param {number|string} timestamp - Unix timestamp in seconds or date string
 * @param {string} dateFormat - Date format string (moment.js style)
 * @param {string} timezone - IANA timezone name
 * @returns {string} Formatted datetime string
 */
function formatDateTime(timestamp, dateFormat, timezone) {
    dateFormat = dateFormat || window.userDateFormat || 'MMM D, YYYY';
    timezone = timezone || window.userTimezone || 'UTC';

    // Normalize to Date
    let date;
    if (typeof timestamp === 'number' || /^\d+$/.test(timestamp)) {
        date = new Date(parseInt(timestamp) * 1000);
    } else {
        date = new Date(timestamp);
    }
    if (isNaN(date.getTime())) return 'Invalid Date';

    const datePart = formatDate(timestamp, dateFormat, timezone);

    // Time via Intl in target timezone
    const timeParts = new Intl.DateTimeFormat('en-US', {
        timeZone: timezone,
        hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true
    }).formatToParts(date);
    const toMap = (arr) => Object.fromEntries(arr.map(p => [p.type, p.value]));
    const m = toMap(timeParts);
    const timePart = `${m.hour}:${m.minute}:${m.second} ${m.dayPeriod || ''}`.trim();
    return `${datePart} ${timePart}`;
}

/**
 * Format author list with intelligent shortening
 * Shows first N and last M authors with "et al." for long lists
 * @param {string} authorString - Author string from database
 * @param {object} options - Formatting options
 * @returns {string} Formatted author string
 */
function formatAuthors(authorString, options = {}) {
    const config = {
        maxDisplay: 3,      // Show all if ≤ this many authors
        firstCount: 1,      // Number of first authors to show
        lastCount: 1,       // Number of last authors to show
        separator: ', ',    // Output separator
        etAl: '…',
        ...options
    };

    // Handle edge cases
    if (!authorString || typeof authorString !== 'string') {
        return authorString || '';
    }

    // Preserve pre-shortened lists (with ellipsis)
    if (/[…\.]{2,}/.test(authorString)) {
        return authorString.replace(/\.{3,}/g, '…').trim();
    }

    // Parse authors based on separator patterns
    let authors;

    // Priority order: semicolon > special comma patterns > and > simple comma
    if (authorString.includes(';')) {
        // Most reliable: semicolon (PubMed format)
        authors = authorString.split(';');
    }
    else if (authorString.includes(',')) {
        // Check for "LastName, Initial." pattern (most common in academic papers)
        if (/[A-Za-z-]+,\s+[A-Z]\./.test(authorString)) {
            // Split after period+comma pattern (end of author with initials)
            // Using replace to insert markers for better browser compatibility
            const markedString = authorString.replace(/\.\s*,\s*(?=[A-Z])/g, '.|SPLIT|');
            authors = markedString.split('|SPLIT|').map(a => a.replace(/\|$/, ''));
        } else {
            // Simple comma split for other formats
            authors = authorString.split(',');
        }

        // Handle "and" in the last element (common pattern)
        const lastIdx = authors.length - 1;
        const lastAuthor = authors[lastIdx];
        if (lastAuthor && / and /i.test(lastAuthor)) {
            const parts = lastAuthor.split(/\s+and\s+/i);
            authors.splice(lastIdx, 1, ...parts);
        }
    }
    else if (/ and /i.test(authorString)) {
        // Only "and" separator
        authors = authorString.split(/\s+and\s+/i);
    }
    else {
        // Single author
        authors = [authorString];
    }

    // Clean up
    authors = authors
        .map(a => a.trim())
        .filter(a => a.length > 0);

    // Format output
    if (authors.length <= config.maxDisplay) {
        return authors.join(config.separator);
    }

    // Shorten with et al.
    const first = authors.slice(0, config.firstCount);
    const last = authors.slice(-config.lastCount);

    // Prevent overlap
    if (config.firstCount + config.lastCount >= authors.length) {
        return authors.join(config.separator);
    }

    return [...first, config.etAl, ...last].join(config.separator);
}

/**
 * Escape HTML characters to prevent XSS attacks
 * @param {string} text - The text to escape
 * @returns {string} HTML-escaped text
 */
function escapeHtml(text) {
    if (!text) return text;
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Safely render HTML with only allowed tags (i, b, em, strong, sup, sub)
 * @param {string} text - The text that may contain HTML
 * @returns {string} Safely rendered HTML
 */
function safeHtml(text) {
    if (!text) return text;

    // First escape all HTML
    let escaped = escapeHtml(text);

    // Define allowed tags and convert them back
    const allowedTags = {
        '&lt;i&gt;(.*?)&lt;/i&gt;': '<i>$1</i>',
        '&lt;b&gt;(.*?)&lt;/b&gt;': '<b>$1</b>',
        '&lt;em&gt;(.*?)&lt;/em&gt;': '<em>$1</em>',
        '&lt;strong&gt;(.*?)&lt;/strong&gt;': '<strong>$1</strong>',
        '&lt;sup&gt;(.*?)&lt;/sup&gt;': '<sup>$1</sup>',
        '&lt;sub&gt;(.*?)&lt;/sub&gt;': '<sub>$1</sub>',
    };

    // Convert back allowed tags
    for (const [pattern, replacement] of Object.entries(allowedTags)) {
        escaped = escaped.replace(new RegExp(pattern, 'gi'), replacement);
    }

    return escaped;
}

/**
 * Handle Details button clicks including middle clicks and Ctrl+clicks
 * @param {Event} event - The mouse event
 * @param {number} feedId - The feed ID to navigate to
 * @returns {boolean} False if event was handled (middle/ctrl click)
 */
function handleDetailsClick(event, feedId) {
    // Middle click (button 1) or Ctrl+Click - open in new tab/window
    if (event.button === 1 || (event.button === 0 && event.ctrlKey)) {
        event.preventDefault();
        window.open(`/paper/${feedId}`, '_blank');
        return false;
    }
}

// Export for use in other files if needed
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { getScoreGradientColor, getSimilarityGradientColor, formatDate, formatDateTime, formatAuthors, handleDetailsClick, escapeHtml, safeHtml };
}
