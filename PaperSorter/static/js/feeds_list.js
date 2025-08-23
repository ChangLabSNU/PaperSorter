// Feeds List JavaScript
// This file handles all the interactive functionality for the feeds list page

// Theme Manager for dark mode
const ThemeManager = {
    init: function() {
        const savedTheme = window.feedsConfig.userTheme || 'light';
        this.applyTheme(savedTheme);
    },

    applyTheme: function(theme) {
        document.body.setAttribute('data-theme', theme);
        this.updateThemeIcon(theme);
        localStorage.setItem('theme', theme);
    },

    toggleTheme: function() {
        const current = document.body.getAttribute('data-theme');
        const next = current === 'light' ? 'dark' : 'light';
        this.applyTheme(next);
        this.savePreference(next);
    },

    savePreference: function(theme) {
        if (window.feedsConfig.isAuthenticated) {
            fetch('/api/user/preferences', {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({theme: theme})
            });
        }
    },

    updateThemeIcon: function(theme) {
        const icon = document.querySelector('.theme-icon');
        if (icon) {
            icon.textContent = theme === 'dark' ? '☀️' : '🌙';
        }
    }
};

// Initialize configuration from template
let currentPage = 1;
let isLoading = false;
let hasMore = true;
let currentMinScore = 0.25; // Will be set from config
let lastDateShown = null;
let bookmarkId = null;
let bookmarkInserted = false;
let userTimezone = '';

// Initialize from config when DOM is ready
function initializeFromConfig() {
    currentMinScore = window.feedsConfig.minScore || 0.25;
    userTimezone = window.feedsConfig.userTimezone || '';
    bookmarkId = window.feedsConfig.bookmarkId || null;
}

// Hamburger menu functions
function toggleHamburgerMenu(event) {
    event.stopPropagation();
    const dropdown = document.getElementById('hamburgerDropdown');
    dropdown.classList.toggle('show');
}

function closeHamburgerMenu() {
    const dropdown = document.getElementById('hamburgerDropdown');
    dropdown.classList.remove('show');
}

// Close dropdown when clicking outside
document.addEventListener('click', function(event) {
    const hamburgerMenu = document.querySelector('.hamburger-menu');
    if (hamburgerMenu && !hamburgerMenu.contains(event.target)) {
        closeHamburgerMenu();
    }
});

function formatDateForHeader(dateStr) {
    const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', options);
}

function getGradientColor(score) {
    // Score is between 0 and 1
    // Map to gradient from red (0) -> yellow (0.5) -> green (1)
    let r, g, b;

    if (score < 0.5) {
        // Red to Yellow
        const ratio = score * 2;
        r = 220;
        g = Math.round(50 + (180 * ratio));
        b = 50;
    } else {
        // Yellow to Green
        const ratio = (score - 0.5) * 2;
        r = Math.round(220 - (140 * ratio));
        g = Math.round(230 - (80 * ratio));
        b = 50;
    }

    return `rgb(${r}, ${g}, ${b})`;
}

function calculateSimilarity(scoreDiff) {
    // Convert score difference to similarity percentage
    // If score diff is 0, similarity is 100%
    // If score diff is 1, similarity is 0%
    const maxDiff = 0.3; // Maximum meaningful difference
    const similarity = Math.max(0, Math.min(100, (1 - scoreDiff / maxDiff) * 100));
    return Math.round(similarity);
}

function createFeedElement(feed) {
    const feedDiv = document.createElement('div');
    feedDiv.className = 'feed-item';
    feedDiv.dataset.feedId = feed.id;
    feedDiv.dataset.published = feed.published;

    const isStarred = feed.starred === true;
    const hasPositiveFeedback = feed.user_feedback === 1;
    const hasNegativeFeedback = feed.user_feedback === -1;
    const isBroadcasted = feed.broadcasted === true;

    const hasLabels = isStarred || hasPositiveFeedback || hasNegativeFeedback;

    let headerHTML = `
        <div class="feed-header">
            <div class="badges-container">
                <span class="score-badge" style="background: ${getGradientColor(feed.score)}">
                    ${(feed.score * 100).toFixed(0)}%`;

    // Add icons container if needed
    if (isStarred || isBroadcasted) {
        headerHTML += '<div class="score-icons">';
        if (isStarred) {
            headerHTML += '<span class="score-icon starred" title="Starred">⭐</span>';
        }
        if (isBroadcasted) {
            headerHTML += '<span class="score-icon broadcasted" title="Broadcasted">📨</span>';
        }
        headerHTML += '</div>';
    }

    headerHTML += '</span>';

    // Add similarity badge if applicable
    if (feed.similarity_score !== undefined && feed.similarity_score !== null) {
        const similarity = calculateSimilarity(Math.abs(feed.score - feed.similarity_score));
        headerHTML += `
            <span class="similarity-badge score-badge" title="Similarity to selected paper">
                ${similarity}%
            </span>`;
    }

    headerHTML += '</div>';

    headerHTML += `
            <div class="feed-content">
                <h3 class="feed-title">${feed.title}</h3>
                <div class="feed-meta">
                    ${feed.author ? `<span class="feed-meta-item feed-author" title="${feed.author}">${feed.author}</span>` : ''}
                    <span class="feed-meta-item feed-origin">${feed.origin}</span>
                    <span class="feed-meta-item feed-date">${new Date(feed.published).toLocaleDateString()}</span>
                </div>
            </div>`;

    if (hasLabels) {
        headerHTML += '<div class="feed-labels">';
        if (isStarred) {
            headerHTML += '<span class="label-badge label-starred">⭐ Starred</span>';
        }
        if (hasPositiveFeedback) {
            headerHTML += '<span class="label-badge label-positive">👍 Interested</span>';
        }
        if (hasNegativeFeedback) {
            headerHTML += '<span class="label-badge label-negative">👎 Not Interested</span>';
        }
        headerHTML += '</div>';
    }

    headerHTML += '</div>';

    const detailsHTML = `
        <div class="feed-details">
            <div class="feed-abstract">${feed.content || 'No abstract available.'}</div>
            <div class="feed-actions">
                <a href="${feed.link}" target="_blank" class="btn btn-primary">
                    🔗<span class="btn-text">Open Article</span>
                </a>
                <button class="btn btn-star ${isStarred ? 'starred' : ''}" onclick="toggleStar(${feed.id}, this)">
                    ${isStarred ? '⭐' : '☆'}<span class="btn-text">${isStarred ? 'Starred' : 'Star'}</span>
                </button>
                <button class="btn btn-thumbs-up ${hasPositiveFeedback ? 'active' : ''}"
                        onclick="sendFeedback(${feed.id}, 1, this)">
                    👍<span class="btn-text">Interested</span>
                </button>
                <button class="btn btn-thumbs-down ${hasNegativeFeedback ? 'active' : ''}"
                        onclick="sendFeedback(${feed.id}, -1, this)">
                    👎<span class="btn-text">Not Interested</span>
                </button>
                <button class="btn btn-similar" onclick="findSimilar(${feed.id})">
                    🔍<span class="btn-text">More Like This</span>
                </button>
            </div>
        </div>`;

    feedDiv.innerHTML = headerHTML + detailsHTML;

    // Add click handler for expansion
    const header = feedDiv.querySelector('.feed-header');
    header.addEventListener('click', function(e) {
        // Don't expand if clicking on a link or button
        if (e.target.tagName === 'A' || e.target.tagName === 'BUTTON') {
            return;
        }
        const details = feedDiv.querySelector('.feed-details');
        details.classList.toggle('expanded');
        feedDiv.classList.toggle('expanded');
    });

    return feedDiv;
}

function updateBookmarkButton(enabled = true) {
    const btn = document.getElementById('bookmarkBtn');
    if (btn) {
        if (enabled && bookmarkId) {
            btn.style.display = 'inline-block';
            btn.textContent = '📖 Jump to Bookmark';
        } else {
            btn.style.display = 'none';
        }
    }
}

function jumpToBookmark() {
    if (!bookmarkId) return;

    // Find the bookmark element
    const bookmarkElement = document.querySelector(`[data-feed-id="${bookmarkId}"]`);
    if (bookmarkElement) {
        // Scroll to bookmark
        bookmarkElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // Highlight briefly
        bookmarkElement.style.transition = 'background-color 0.3s';
        bookmarkElement.style.backgroundColor = 'var(--bg-hover)';
        setTimeout(() => {
            bookmarkElement.style.backgroundColor = '';
        }, 1000);
    } else {
        // Bookmark not loaded yet, need to load more feeds
        loadMoreFeeds(true);
    }
}

async function loadFeeds(page = 1, append = false, searchingForBookmark = false) {
    if (isLoading) return;
    isLoading = true;

    const container = document.getElementById('feedsContainer');
    const channelId = document.getElementById('channelSelector')?.value || '';

    if (!append) {
        container.innerHTML = '<div class="loading"><div class="loading-spinner"></div>Loading feeds...</div>';
        lastDateShown = null;
        bookmarkInserted = false;
    }

    try {
        const params = new URLSearchParams({
            page: page.toString(),
            min_score: currentMinScore.toString(),
            channel_id: channelId
        });

        if (searchingForBookmark && bookmarkId) {
            params.append('include_bookmark', 'true');
        }

        const response = await fetch(`/api/feeds?${params}`);
        const data = await response.json();

        if (!append) {
            container.innerHTML = '';
        } else {
            // Remove loading indicator if exists
            const loadingDiv = container.querySelector('.loading');
            if (loadingDiv) loadingDiv.remove();
        }

        // Update bookmark info
        if (data.bookmark_id && !bookmarkId) {
            bookmarkId = data.bookmark_id;
            updateBookmarkButton();
        }

        const feedsToDisplay = [];
        const bookmarkDate = data.bookmark_date ? new Date(data.bookmark_date).toDateString() : null;

        data.feeds.forEach(feed => {
            const feedDate = new Date(feed.published).toDateString();

            // Check if we need to insert bookmark divider
            if (!bookmarkInserted && bookmarkDate && bookmarkId) {
                const currentFeedDate = new Date(feed.published);
                const bookmarkDateObj = new Date(data.bookmark_date);

                if (currentFeedDate < bookmarkDateObj) {
                    // Insert bookmark divider before this feed
                    const divider = document.createElement('div');
                    divider.className = 'bookmark-divider';
                    divider.id = 'bookmarkDivider';
                    divider.innerHTML = 'Last Read Position';
                    container.appendChild(divider);
                    bookmarkInserted = true;
                }
            }

            // Add date header if needed
            if (feedDate !== lastDateShown) {
                const dateHeader = document.createElement('div');
                dateHeader.className = 'date-header';
                dateHeader.textContent = formatDateForHeader(feed.published);
                container.appendChild(dateHeader);
                lastDateShown = feedDate;
            }

            // Add feed element
            const feedElement = createFeedElement(feed);
            container.appendChild(feedElement);
        });

        // Insert bookmark at the end if not yet inserted and we have no more feeds
        if (!bookmarkInserted && bookmarkId && data.feeds.length === 0) {
            const divider = document.createElement('div');
            divider.className = 'bookmark-divider';
            divider.id = 'bookmarkDivider';
            divider.innerHTML = 'Last Read Position';
            container.appendChild(divider);
            bookmarkInserted = true;
        }

        hasMore = data.has_more;
        currentPage = page;

        // If searching for bookmark and haven't found it yet, continue loading
        if (searchingForBookmark && !bookmarkInserted && hasMore) {
            await loadFeeds(page + 1, true, true);
        }

    } catch (error) {
        console.error('Failed to load feeds:', error);
        if (!append) {
            container.innerHTML = '<div class="error">Failed to load feeds. Please try again.</div>';
        }
    } finally {
        isLoading = false;
    }
}

function loadMoreFeeds(searchingForBookmark = false) {
    if (hasMore && !isLoading) {
        loadFeeds(currentPage + 1, true, searchingForBookmark);
    }
}

// Infinite scroll
window.addEventListener('scroll', () => {
    if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 1000) {
        loadMoreFeeds();
    }
});

// Score filter
function updateScoreFilter(value) {
    currentMinScore = parseFloat(value);
    document.getElementById('scoreValue').textContent = (currentMinScore * 100).toFixed(0) + '%';

    // Debounce the reload
    clearTimeout(window.scoreFilterTimeout);
    window.scoreFilterTimeout = setTimeout(() => {
        currentPage = 1;
        hasMore = true;
        loadFeeds(1, false);
    }, 500);
}

// Channel selector
function onChannelChange() {
    currentPage = 1;
    hasMore = true;
    loadFeeds(1, false);
}

// Star/unstar functionality
async function toggleStar(feedId, button) {
    const isStarred = button.classList.contains('starred');

    try {
        const response = await fetch(`/api/feeds/${feedId}/star`, {
            method: isStarred ? 'DELETE' : 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (response.ok) {
            button.classList.toggle('starred');
            const btnText = button.querySelector('.btn-text');
            if (btnText) {
                btnText.textContent = isStarred ? 'Star' : 'Starred';
            }
            button.innerHTML = (isStarred ? '☆' : '⭐') +
                '<span class="btn-text">' + (isStarred ? 'Star' : 'Starred') + '</span>';

            // Update label in header
            const feedItem = button.closest('.feed-item');
            updateFeedLabels(feedItem, 'starred', !isStarred);

            // Update icon in score badge
            const scoreIcons = feedItem.querySelector('.score-icons');
            const starIcon = scoreIcons?.querySelector('.starred');

            if (!isStarred) {
                // Add star icon
                if (!scoreIcons) {
                    const scoreBadge = feedItem.querySelector('.score-badge');
                    const iconsDiv = document.createElement('div');
                    iconsDiv.className = 'score-icons';
                    iconsDiv.innerHTML = '<span class="score-icon starred" title="Starred">⭐</span>';
                    scoreBadge.appendChild(iconsDiv);
                } else if (!starIcon) {
                    scoreIcons.insertAdjacentHTML('afterbegin',
                        '<span class="score-icon starred" title="Starred">⭐</span>');
                }
            } else {
                // Remove star icon
                if (starIcon) {
                    starIcon.remove();
                    // Remove icons container if empty
                    if (scoreIcons && scoreIcons.children.length === 0) {
                        scoreIcons.remove();
                    }
                }
            }

            showToast(isStarred ? 'Removed star' : 'Added star', 'success');
        }
    } catch (error) {
        console.error('Failed to toggle star:', error);
        showToast('Failed to update star', 'error');
    }
}

// Feedback functionality
async function sendFeedback(feedId, score, button) {
    const feedItem = button.closest('.feed-item');
    const isActive = button.classList.contains('active');

    try {
        const response = await fetch(`/api/feeds/${feedId}/feedback`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                score: isActive ? 0 : score
            })
        });

        if (response.ok) {
            // Update button states
            const thumbsUp = feedItem.querySelector('.btn-thumbs-up');
            const thumbsDown = feedItem.querySelector('.btn-thumbs-down');

            if (isActive) {
                // Remove feedback
                button.classList.remove('active');
                updateFeedLabels(feedItem, score > 0 ? 'positive' : 'negative', false);
            } else {
                // Add/change feedback
                thumbsUp.classList.toggle('active', score > 0);
                thumbsDown.classList.toggle('active', score < 0);

                // Update labels
                updateFeedLabels(feedItem, 'positive', score > 0);
                updateFeedLabels(feedItem, 'negative', score < 0);
            }

            showToast(
                isActive ? 'Feedback removed' :
                    (score > 0 ? 'Marked as interested' : 'Marked as not interested'),
                'success'
            );
        }
    } catch (error) {
        console.error('Failed to send feedback:', error);
        showToast('Failed to update feedback', 'error');
    }
}

function updateFeedLabels(feedItem, type, add) {
    let labelsContainer = feedItem.querySelector('.feed-labels');

    if (add) {
        if (!labelsContainer) {
            labelsContainer = document.createElement('div');
            labelsContainer.className = 'feed-labels';
            feedItem.querySelector('.feed-header').appendChild(labelsContainer);
        }

        // Remove opposite label if exists
        if (type === 'positive') {
            const negLabel = labelsContainer.querySelector('.label-negative');
            if (negLabel) negLabel.remove();
        } else if (type === 'negative') {
            const posLabel = labelsContainer.querySelector('.label-positive');
            if (posLabel) posLabel.remove();
        }

        // Add new label if not exists
        const existingLabel = labelsContainer.querySelector(`.label-${type}`);
        if (!existingLabel) {
            const label = document.createElement('span');
            label.className = `label-badge label-${type}`;
            if (type === 'starred') {
                label.textContent = '⭐ Starred';
            } else if (type === 'positive') {
                label.textContent = '👍 Interested';
            } else if (type === 'negative') {
                label.textContent = '👎 Not Interested';
            }
            labelsContainer.appendChild(label);
        }
    } else {
        // Remove label
        if (labelsContainer) {
            const label = labelsContainer.querySelector(`.label-${type}`);
            if (label) {
                label.remove();
                // Remove container if empty
                if (labelsContainer.children.length === 0) {
                    labelsContainer.remove();
                }
            }
        }
    }
}

// Find similar articles
async function findSimilar(feedId) {
    window.location.href = `/similar/${feedId}`;
}

// Toast notification
function showToast(message, type = 'success') {
    const existingToast = document.querySelector('.toast');
    if (existingToast) {
        existingToast.remove();
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    // Trigger animation
    setTimeout(() => toast.classList.add('show'), 10);

    // Remove after 3 seconds
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Search functionality
let searchMode = 'semantic';
let isSearching = false;

function toggleGeneralSearch() {
    const searchDiv = document.getElementById('generalSearchInterface');
    if (searchDiv.style.display === 'none') {
        searchDiv.style.display = 'block';
        document.getElementById('generalSearchInput').focus();
    } else {
        searchDiv.style.display = 'none';
    }
}

function toggleSemanticSearch() {
    const searchDiv = document.getElementById('semanticSearchInterface');
    if (searchDiv.style.display === 'none') {
        searchDiv.style.display = 'block';
        const textarea = document.getElementById('semanticSearchInput');
        textarea.focus();
    } else {
        searchDiv.style.display = 'none';
    }
}

async function performGeneralSearch() {
    const query = document.getElementById('generalSearchInput').value.trim();
    if (!query) return;

    const searchInterface = document.getElementById('generalSearchInterface');
    const feedsSection = document.getElementById('feedsSection');
    const resultsSection = document.getElementById('searchResultsSection');
    const resultsContainer = document.getElementById('searchResultsContainer');

    // Update URL
    const newUrl = new URL(window.location);
    newUrl.searchParams.set('q', query);
    window.history.pushState({}, '', newUrl);

    // Show loading
    resultsContainer.innerHTML = '<div class="loading"><div class="loading-spinner"></div>Searching...</div>';
    searchInterface.style.display = 'none';
    feedsSection.style.display = 'none';
    resultsSection.style.display = 'block';

    try {
        const response = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query, type: 'text' })
        });

        const data = await response.json();
        displaySearchResults(data.results, query);
    } catch (error) {
        resultsContainer.innerHTML = '<div class="error">Search failed. Please try again.</div>';
    }
}

async function performSemanticSearch() {
    const input = document.getElementById('semanticSearchInput');
    const query = input.value.trim();
    if (!query) return;

    const searchInterface = document.getElementById('semanticSearchInterface');
    const feedsSection = document.getElementById('feedsSection');
    const resultsSection = document.getElementById('searchResultsSection');
    const resultsContainer = document.getElementById('searchResultsContainer');

    // Update URL
    const newUrl = new URL(window.location);
    newUrl.searchParams.set('q', query);
    window.history.pushState({}, '', newUrl);

    // Show loading
    resultsContainer.innerHTML = '<div class="loading"><div class="loading-spinner"></div>Processing semantic search...</div>';
    searchInterface.style.display = 'none';
    feedsSection.style.display = 'none';
    resultsSection.style.display = 'block';

    try {
        const response = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query, type: 'semantic' })
        });

        const data = await response.json();
        displaySearchResults(data.results, 'Semantic Search');

        // Generate summary and poster if admin
        if (window.feedsConfig.isAdmin && data.results.length > 0) {
            generateSummary(data.results);
            generatePoster(data.results);
        }
    } catch (error) {
        resultsContainer.innerHTML = '<div class="error">Search failed. Please try again.</div>';
    }
}

async function searchSemanticScholar() {
    const input = document.getElementById('semanticSearchInput');
    const query = input.value.trim();
    if (!query || isSearching) return;

    isSearching = true;
    const searchBtn = event.target;
    const originalText = searchBtn.innerHTML;
    searchBtn.innerHTML = '<span class="loading-spinner" style="display:inline-block;width:16px;height:16px;margin-right:5px;"></span>Searching...';
    searchBtn.disabled = true;

    const searchInterface = document.getElementById('semanticSearchInterface');
    const feedsSection = document.getElementById('feedsSection');
    const resultsSection = document.getElementById('searchResultsSection');
    const resultsContainer = document.getElementById('searchResultsContainer');

    resultsContainer.innerHTML = '<div class="loading"><div class="loading-spinner"></div>Searching academic databases...</div>';
    searchInterface.style.display = 'none';
    feedsSection.style.display = 'none';
    resultsSection.style.display = 'block';

    try {
        const response = await fetch('/api/search/semantic-scholar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query })
        });

        if (!response.ok) throw new Error('Search failed');

        const data = await response.json();
        displayAcademicResults(data.results);
    } catch (error) {
        console.error('Search error:', error);
        resultsContainer.innerHTML = '<div class="error">Failed to search academic databases. Please try again.</div>';
    } finally {
        searchBtn.innerHTML = originalText;
        searchBtn.disabled = false;
        isSearching = false;
    }
}

function displaySearchResults(results, searchQuery) {
    const container = document.getElementById('searchResultsContainer');
    const queryDisplay = document.getElementById('searchQuery');

    if (queryDisplay) {
        queryDisplay.textContent = searchQuery;
    }

    if (!results || results.length === 0) {
        container.innerHTML = '<div class="no-results">No results found</div>';
        return;
    }

    container.innerHTML = results.map(result => `
        <div class="feed-item">
            <div class="feed-header">
                <div class="badges-container">
                    <span class="score-badge" style="background: ${getGradientColor(result.score)}">
                        ${(result.score * 100).toFixed(0)}%
                    </span>
                </div>
                <div class="feed-content">
                    <h3 class="feed-title">${result.title}</h3>
                    <div class="feed-meta">
                        ${result.author ? `<span class="feed-meta-item feed-author">${result.author}</span>` : ''}
                        <span class="feed-meta-item feed-origin">${result.origin}</span>
                        <span class="feed-meta-item feed-date">${new Date(result.published).toLocaleDateString()}</span>
                    </div>
                </div>
            </div>
            <div class="feed-details expanded">
                <div class="feed-abstract">${result.content || 'No abstract available.'}</div>
                <div class="feed-actions">
                    <a href="${result.link}" target="_blank" class="btn btn-primary">
                        🔗 Open Article
                    </a>
                    <button class="btn btn-similar" onclick="findSimilar(${result.id})">
                        🔍 More Like This
                    </button>
                </div>
            </div>
        </div>
    `).join('');
}

function displayAcademicResults(results) {
    const container = document.getElementById('searchResultsContainer');

    if (!results || results.length === 0) {
        container.innerHTML = '<div class="no-results">No academic papers found</div>';
        return;
    }

    container.innerHTML = results.map(paper => {
        const isAlreadyAdded = paper.already_in_db;
        return `
            <div class="search-result-item">
                <div class="search-result-title">${paper.title}</div>
                <div class="search-result-meta">
                    ${paper.authors ? paper.authors.join(', ') : 'Unknown authors'}
                    ${paper.year ? ` • ${paper.year}` : ''}
                    ${paper.venue ? ` • ${paper.venue}` : ''}
                </div>
                <div class="search-result-abstract">
                    ${paper.abstract || 'No abstract available'}
                </div>
                <div class="search-result-actions">
                    ${paper.url ? `<a href="${paper.url}" target="_blank" class="btn btn-primary">🔗 View Paper</a>` : ''}
                    ${isAlreadyAdded ?
            '<span class="already-added-badge">✓ Already in database</span>' :
            `<button class="btn btn-add" onclick="addPaperToDatabase('${paper.paperId}', this)">
                        ➕ Add to Database
                     </button>`
        }
                </div>
            </div>
        `;
    }).join('');
}

async function addPaperToDatabase(paperId, button) {
    button.disabled = true;
    button.textContent = 'Adding...';

    try {
        const response = await fetch('/api/search/add-paper', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ paper_id: paperId })
        });

        if (response.ok) {
            button.textContent = '✓ Added';
            button.classList.add('btn-success');
            button.disabled = true;
            showToast('Paper added successfully', 'success');
        } else {
            throw new Error('Failed to add paper');
        }
    } catch (error) {
        button.disabled = false;
        button.textContent = '➕ Add to Database';
        showToast('Failed to add paper', 'error');
    }
}

function backToFeeds() {
    const feedsSection = document.getElementById('feedsSection');
    const resultsSection = document.getElementById('searchResultsSection');

    feedsSection.style.display = 'block';
    resultsSection.style.display = 'none';

    // Clear URL parameters
    const newUrl = new URL(window.location);
    newUrl.searchParams.delete('q');
    window.history.pushState({}, '', newUrl);
}

// Summary generation
async function generateSummary(papers) {
    const summaryContent = document.getElementById('summaryContent');
    if (!summaryContent) return;

    summaryContent.innerHTML = '<div class="summary-loading"><div class="spinner"></div><p>Generating AI summary...</p></div>';

    try {
        const response = await fetch('/api/search/summarize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                papers: papers.slice(0, 10).map(p => ({
                    title: p.title,
                    abstract: p.content,
                    authors: p.author
                }))
            })
        });

        if (!response.ok) throw new Error('Summary generation failed');

        const data = await response.json();
        summaryContent.innerHTML = `
            <div class="summary-text">${data.summary}</div>
            <div class="summary-disclaimer">
                <p><strong>Note:</strong> This summary was generated by AI and may contain inaccuracies.
                Always refer to the original papers for authoritative information.</p>
            </div>
        `;
    } catch (error) {
        console.error('Summary generation error:', error);
        summaryContent.innerHTML = '<div class="error">Failed to generate summary</div>';
    }
}

// Poster generation
async function generatePoster(papers) {
    const posterContent = document.getElementById('posterContent');
    if (!posterContent) return;

    posterContent.innerHTML = '<div class="poster-loading"><div class="spinner"></div><p>Creating infographic poster...</p></div>';

    try {
        const response = await fetch('/api/user/poster', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                papers: papers.slice(0, 10).map(p => ({
                    title: p.title,
                    abstract: p.content,
                    authors: p.author
                }))
            })
        });

        if (!response.ok) throw new Error('Poster generation failed');

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);

        posterContent.innerHTML = `
            <iframe src="${url}" class="poster-iframe" title="Research Poster"></iframe>
        `;
    } catch (error) {
        console.error('Poster generation error:', error);
        posterContent.innerHTML = '<div class="error">Failed to generate poster</div>';
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    // Initialize from config
    initializeFromConfig();

    // Initialize theme
    ThemeManager.init();

    // Check for search query in URL
    const urlParams = new URLSearchParams(window.location.search);
    const searchQuery = urlParams.get('q');

    if (searchQuery) {
        // Restore search from URL
        document.getElementById('semanticSearchInput').value = searchQuery;
        performSemanticSearch();
    } else {
        // Load initial feeds
        loadFeeds();
    }

    // Update bookmark button visibility
    updateBookmarkButton();

    // Initialize score filter
    const scoreSlider = document.getElementById('scoreSlider');
    if (scoreSlider) {
        scoreSlider.value = currentMinScore;
        document.getElementById('scoreValue').textContent = (currentMinScore * 100).toFixed(0) + '%';
    }
});