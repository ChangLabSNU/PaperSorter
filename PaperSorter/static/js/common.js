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
    // Default values
    format = format || window.userDateFormat || 'MMM D, YYYY';
    timezone = timezone || window.userTimezone || 'UTC';

    // Convert timestamp to Date object
    let date;
    if (typeof timestamp === 'number' || /^\d+$/.test(timestamp)) {
        // Unix timestamp in seconds
        date = new Date(parseInt(timestamp) * 1000);
    } else {
        date = new Date(timestamp);
    }

    // Check if date is valid
    if (isNaN(date.getTime())) {
        return 'Invalid Date';
    }

    // Basic format replacements (simplified version)
    // For full functionality, would need moment.js or similar
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const fullMonths = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

    const year = date.getFullYear();
    const month = date.getMonth();
    const day = date.getDate();
    const monthStr = (month + 1).toString().padStart(2, '0');
    const dayStr = day.toString().padStart(2, '0');

    let formatted = format;
    formatted = formatted.replace('YYYY', year);
    formatted = formatted.replace('MMM', months[month]);
    formatted = formatted.replace('MM', monthStr);
    formatted = formatted.replace('M', month + 1);
    formatted = formatted.replace('DD', dayStr);
    formatted = formatted.replace('D', day);
    formatted = formatted.replace('年', '年');
    formatted = formatted.replace('月', '月');
    formatted = formatted.replace('日', '日');

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
    // Default values
    dateFormat = dateFormat || window.userDateFormat || 'MMM D, YYYY';
    timezone = timezone || window.userTimezone || 'UTC';

    // Convert timestamp to Date object
    let date;
    if (typeof timestamp === 'number' || /^\d+$/.test(timestamp)) {
        // Unix timestamp in seconds
        date = new Date(parseInt(timestamp) * 1000);
    } else {
        date = new Date(timestamp);
    }

    // Check if date is valid
    if (isNaN(date.getTime())) {
        return 'Invalid Date';
    }

    // Format date part
    const datePart = formatDate(timestamp, dateFormat, timezone);

    // Format time part (fixed format: HH:MM:SS AM/PM)
    let hours = date.getHours();
    const minutes = date.getMinutes().toString().padStart(2, '0');
    const seconds = date.getSeconds().toString().padStart(2, '0');
    const ampm = hours >= 12 ? 'PM' : 'AM';
    hours = hours % 12;
    hours = hours ? hours : 12; // the hour '0' should be '12'
    const hoursStr = hours.toString();

    const timePart = `${hoursStr}:${minutes}:${seconds} ${ampm}`;

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

// Export for use in other files if needed
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { getScoreGradientColor, getSimilarityGradientColor, formatDate, formatDateTime, formatAuthors };
}