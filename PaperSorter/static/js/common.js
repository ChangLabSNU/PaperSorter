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

// Export for use in other files if needed
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { getScoreGradientColor, getSimilarityGradientColor };
}