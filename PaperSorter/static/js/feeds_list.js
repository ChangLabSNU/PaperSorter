// Feeds List JavaScript
// This file handles all the interactive functionality for the feeds list page

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

function formatDateForHeader(dateInput) {
    const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    // dateInput is already converted to milliseconds when called
    const date = new Date(dateInput);
    return date.toLocaleDateString('en-US', options);
}

// Use the common gradient color function
function getGradientColor(score) {
    return getScoreGradientColor(score);
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
    feedDiv.dataset.feedId = feed.rowid;
    feedDiv.dataset.published = feed.published;

    const isStarred = feed.starred === true;
    const hasPositiveFeedback = feed.label === 1;
    const hasNegativeFeedback = feed.label === 0;
    const isBroadcasted = feed.broadcasted === true;

    const hasLabels = isStarred;  // Only show starred label now

    let headerHTML = `
        <div class="feed-header">
            <div class="badges-container">
                <span class="score-badge" style="background: ${getGradientColor(feed.score)}">
                    ${(feed.score * 100).toFixed(0)}`;

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
                ${similarity}
            </span>`;
    }

    headerHTML += '</div>';

    headerHTML += `
            <div class="feed-content">
                <h3 class="feed-title">${feed.title}</h3>
                <div class="feed-meta">
                    <span class="feed-meta-item feed-origin">${feed.origin}</span>
                    ${feed.author ? `<span class="feed-meta-item feed-author" title="${feed.author}">${feed.author}</span>` : ''}
                    <span class="feed-meta-item feed-date">${new Date(feed.published * 1000).toLocaleDateString()}</span>
                </div>
            </div>`;
    
    // Add vote count badges on the far right
    headerHTML += '<div class="vote-badges-container">';
    if (feed.positive_votes > 0) {
        headerHTML += `
            <span class="vote-badge vote-positive" title="${feed.positive_votes} interested">
                +${feed.positive_votes}
            </span>`;
    }
    if (feed.negative_votes > 0) {
        headerHTML += `
            <span class="vote-badge vote-negative" title="${feed.negative_votes} not interested">
                −${feed.negative_votes}
            </span>`;
    }
    headerHTML += '</div>';

    if (hasLabels) {
        headerHTML += '<div class="feed-labels">';
        if (isStarred) {
            headerHTML += '<span class="label-badge label-starred" title="Starred">⭐</span>';
        }
        headerHTML += '</div>';
    }

    headerHTML += '</div>';

    const detailsHTML = `
        <div class="feed-details">
            <div class="feed-abstract">Click to load abstract...</div>
            <div class="feed-actions">
                <a href="${feed.link}" target="_blank" class="btn btn-primary">
                    🔗<span class="btn-text">Open Article</span>
                </a>
                <button class="btn btn-star ${isStarred ? 'starred' : ''}" onclick="toggleStar(${feed.rowid}, this)">
                    ${isStarred ? '⭐' : '☆'}<span class="btn-text">${isStarred ? 'Starred' : 'Star'}</span>
                </button>
                <button class="btn btn-thumbs-up ${hasPositiveFeedback ? 'active' : ''}"
                        onclick="sendFeedback(${feed.rowid}, 1, this)">
                    👍<span class="btn-text">Interested</span>
                </button>
                <button class="btn btn-thumbs-down ${hasNegativeFeedback ? 'active' : ''}"
                        onclick="sendFeedback(${feed.rowid}, 0, this)">
                    👎<span class="btn-text">Not Interested</span>
                </button>
                <button class="btn btn-similar" onclick="findSimilar(${feed.rowid})">
                    🔍<span class="btn-text">More Like This</span>
                </button>
            </div>
        </div>`;

    feedDiv.innerHTML = headerHTML + detailsHTML;

    // Add click handler for expansion
    const header = feedDiv.querySelector('.feed-header');
    header.addEventListener('click', async function(e) {
        // Don't expand if clicking on a link or button
        if (e.target.tagName === 'A' || e.target.tagName === 'BUTTON') {
            return;
        }
        const details = feedDiv.querySelector('.feed-details');
        const abstract = details.querySelector('.feed-abstract');

        // Toggle expansion
        details.classList.toggle('expanded');
        feedDiv.classList.toggle('expanded');

        // Load content if expanding and not already loaded
        if (details.classList.contains('expanded') && !abstract.dataset.loaded) {
            abstract.innerHTML = '<div class="loading">Loading abstract...</div>';
            try {
                const response = await fetch(`/api/feeds/${feed.rowid}/content`);
                if (response.ok) {
                    const data = await response.json();
                    abstract.innerHTML = data.content || data.tldr || 'No abstract available.';
                    abstract.dataset.loaded = 'true';
                } else {
                    abstract.innerHTML = 'Failed to load abstract.';
                }
            } catch (error) {
                abstract.innerHTML = 'Error loading abstract.';
            }
        }
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

        data.feeds.forEach(feed => {
            const feedDate = new Date(feed.published * 1000).toDateString();

            // Check if we need to insert bookmark divider
            if (!bookmarkInserted && bookmarkId && feed.rowid === bookmarkId) {
                // Insert bookmark divider before this feed (this is where user was)
                const divider = document.createElement('div');
                divider.className = 'bookmark-divider';
                divider.id = 'bookmarkDivider';
                divider.innerHTML = 'You were here';
                container.appendChild(divider);
                bookmarkInserted = true;
            }

            // Add date header if needed
            if (feedDate !== lastDateShown) {
                const dateHeader = document.createElement('div');
                dateHeader.className = 'date-header';
                dateHeader.textContent = formatDateForHeader(feed.published * 1000);
                container.appendChild(dateHeader);
                lastDateShown = feedDate;
            }

            // Add feed element
            const feedElement = createFeedElement(feed);
            container.appendChild(feedElement);
        });

        // Don't insert bookmark at the end - it should only appear at the actual position

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
    // Convert slider value (0-4) to actual score threshold
    const sliderIndex = parseInt(value);
    currentMinScore = window.feedsConfig.scoreThresholds[sliderIndex];

    // Update display with score label
    const scoreLabel = window.feedsConfig.scoreLabels[sliderIndex];
    document.getElementById('scoreValue').textContent = scoreLabel;

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
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                starred: !isStarred
            })
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

        }
    } catch (error) {
        console.error('Failed to toggle star:', error);
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
                score: isActive ? null : score
            })
        });

        if (response.ok) {
            // Update button states
            const thumbsUp = feedItem.querySelector('.btn-thumbs-up');
            const thumbsDown = feedItem.querySelector('.btn-thumbs-down');
            
            // Update vote count badges
            let voteBadgesContainer = feedItem.querySelector('.vote-badges-container');
            if (!voteBadgesContainer) {
                // Create container if it doesn't exist
                voteBadgesContainer = document.createElement('div');
                voteBadgesContainer.className = 'vote-badges-container';
                feedItem.querySelector('.feed-header').appendChild(voteBadgesContainer);
            }
            
            // Get current vote badges
            let positiveBadge = voteBadgesContainer.querySelector('.vote-positive');
            let negativeBadge = voteBadgesContainer.querySelector('.vote-negative');
            
            // Parse current counts
            let positiveCount = positiveBadge ? parseInt(positiveBadge.textContent.substring(1)) : 0;
            let negativeCount = negativeBadge ? parseInt(negativeBadge.textContent.substring(1)) : 0;
            
            if (isActive) {
                // Remove feedback - decrement the appropriate counter
                button.classList.remove('active');
                if (score === 1) {
                    positiveCount = Math.max(0, positiveCount - 1);
                } else if (score === 0) {
                    negativeCount = Math.max(0, negativeCount - 1);
                }
            } else {
                // Check if switching from one to another
                if (thumbsUp.classList.contains('active') && score === 0) {
                    // Switching from positive to negative
                    positiveCount = Math.max(0, positiveCount - 1);
                    negativeCount++;
                } else if (thumbsDown.classList.contains('active') && score === 1) {
                    // Switching from negative to positive
                    negativeCount = Math.max(0, negativeCount - 1);
                    positiveCount++;
                } else {
                    // New vote
                    if (score === 1) {
                        positiveCount++;
                    } else if (score === 0) {
                        negativeCount++;
                    }
                }
                
                // Update button states
                thumbsUp.classList.toggle('active', score === 1);
                thumbsDown.classList.toggle('active', score === 0);
            }
            
            // Update or remove positive badge
            if (positiveCount > 0) {
                if (!positiveBadge) {
                    positiveBadge = document.createElement('span');
                    positiveBadge.className = 'vote-badge vote-positive';
                    voteBadgesContainer.appendChild(positiveBadge);
                }
                positiveBadge.textContent = `+${positiveCount}`;
                positiveBadge.title = `${positiveCount} interested`;
            } else if (positiveBadge) {
                positiveBadge.remove();
            }
            
            // Update or remove negative badge
            if (negativeCount > 0) {
                if (!negativeBadge) {
                    negativeBadge = document.createElement('span');
                    negativeBadge.className = 'vote-badge vote-negative';
                    voteBadgesContainer.appendChild(negativeBadge);
                }
                negativeBadge.textContent = `−${negativeCount}`;
                negativeBadge.title = `${negativeCount} not interested`;
            } else if (negativeBadge) {
                negativeBadge.remove();
            }

        }
    } catch (error) {
        console.error('Failed to send feedback:', error);
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
                label.textContent = '⭐';
                label.title = 'Starred';
            } else if (type === 'positive') {
                // No longer used - we use vote badges instead
                return;
            } else if (type === 'negative') {
                // No longer used - we use vote badges instead
                return;
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
    const searchDiv = document.getElementById('generalSearchContainer');
    if (searchDiv.style.display === 'none') {
        searchDiv.style.display = 'block';
        document.getElementById('generalSearchInput').focus();
    } else {
        searchDiv.style.display = 'none';
    }
}

function toggleSemanticSearch() {
    const searchDiv = document.getElementById('semanticSearchContainer');
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

    const searchInterface = document.getElementById('generalSearchContainer');
    const feedsSection = document.getElementById('feedsContainer');
    const resultsSection = document.getElementById('generalSearchResultsContainer');
    const resultsContainer = document.getElementById('generalSearchResults');

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

        if (!response.ok) {
            throw new Error(`Search failed: ${response.status}`);
        }

        const data = await response.json();
        currentSearchShortName = data.short_name;
        displaySearchResults(data.feeds, query);
    } catch (error) {
        console.error('Search error:', error);
        resultsContainer.innerHTML = '<div class="error">Search failed. Please try again.</div>';
    }
}


async function searchSemanticScholar(event) {
    const input = document.getElementById('semanticSearchInput');
    const query = input.value.trim();
    if (!query || isSearching) return;

    isSearching = true;
    const searchBtn = event ? event.target : document.querySelector('#semanticSearchContainer .btn-primary');
    const originalText = searchBtn.innerHTML;
    searchBtn.innerHTML = '<span class="loading-spinner" style="display:inline-block;width:16px;height:16px;margin-right:5px;"></span>Searching...';
    searchBtn.disabled = true;

    const searchInterface = document.getElementById('semanticSearchContainer');
    const feedsSection = document.getElementById('feedsContainer');
    const resultsSection = document.getElementById('searchResultsContainer');
    const resultsContainer = document.getElementById('searchResults');

    resultsContainer.innerHTML = '<div class="loading"><div class="loading-spinner"></div>Searching academic databases...</div>';
    searchInterface.style.display = 'none';
    feedsSection.style.display = 'none';
    resultsSection.style.display = 'block';

    try {
        const response = await fetch('/api/scholarly-database/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query })
        });

        if (!response.ok) throw new Error('Search failed');

        const data = await response.json();
        displayAcademicResults(data.papers || data.results || []);
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
    // Store results for AI Summary generation
    currentSearchResults = results || [];
    
    // Determine which container to use based on what's visible
    let container = document.getElementById('generalSearchResults');
    if (!container || container.parentElement.style.display === 'none') {
        container = document.getElementById('searchResults');
    }
    
    const queryDisplay = document.getElementById('searchQueryDisplay');
    if (queryDisplay) {
        queryDisplay.textContent = `Search: "${searchQuery}"`;
    }
    
    // Show AI Summary section if admin and has results
    const summarySection = document.getElementById('searchSummarySection');
    if (summarySection) {
        if (window.feedsConfig.isAdmin && results && results.length > 0) {
            summarySection.style.display = 'block';
            // Reset to initial state
            document.getElementById('searchSummaryInitial').style.display = 'flex';
            document.getElementById('searchSummaryLoading').style.display = 'none';
            document.getElementById('searchPosterLoading').style.display = 'none';
            document.getElementById('searchSummaryText').style.display = 'none';
            document.getElementById('searchPosterContent').style.display = 'none';
        } else {
            summarySection.style.display = 'none';
        }
    }

    if (!results || results.length === 0) {
        container.innerHTML = '<div class="no-results">No results found</div>';
        return;
    }

    // First, create the HTML
    container.innerHTML = results.map(result => `
        <div class="feed-item" data-feed-id="${result.rowid || result.id}">
            <div class="feed-header">
                <div class="badges-container">
                    ${result.similarity !== undefined && result.similarity !== null ? `
                        <span class="similarity-badge score-badge" title="Similarity to search query">
                            ${Math.round(result.similarity * 100)}
                        </span>
                    ` : ''}
                    <span class="score-badge" style="background: ${getGradientColor(result.score)}">
                        ${(result.score * 100).toFixed(0)}
                    </span>
                </div>
                <div class="feed-content">
                    <h3 class="feed-title">${result.title}</h3>
                    <div class="feed-meta">
                        <span class="feed-meta-item feed-origin">${result.origin}</span>
                        ${result.author ? `<span class="feed-meta-item feed-author">${result.author}</span>` : ''}
                        <span class="feed-meta-item feed-date">${new Date(result.published * 1000).toLocaleDateString()}</span>
                    </div>
                </div>
            </div>
            <div class="feed-details">
                <div class="feed-abstract">Click to load abstract...</div>
                <div class="feed-actions">
                    <a href="${result.link}" target="_blank" class="btn btn-primary">
                        🔗<span class="btn-text">Open Article</span>
                    </a>
                    <button class="btn btn-star ${result.starred ? 'starred' : ''}" onclick="toggleStar(${result.rowid || result.id}, this)">
                        ${result.starred ? '⭐' : '☆'}<span class="btn-text">${result.starred ? 'Starred' : 'Star'}</span>
                    </button>
                    <button class="btn btn-thumbs-up ${result.label === 1 ? 'active' : ''}"
                            onclick="sendFeedback(${result.rowid || result.id}, 1, this)">
                        👍<span class="btn-text">Interested</span>
                    </button>
                    <button class="btn btn-thumbs-down ${result.label === -1 ? 'active' : ''}"
                            onclick="sendFeedback(${result.rowid || result.id}, -1, this)">
                        👎<span class="btn-text">Not Interested</span>
                    </button>
                    <button class="btn btn-similar" onclick="findSimilar(${result.rowid || result.id})">
                        🔍<span class="btn-text">More Like This</span>
                    </button>
                </div>
            </div>
        </div>
    `).join('');
    
    // Then, add event listeners to all feed items
    container.querySelectorAll('.feed-item').forEach(feedDiv => {
        const feedId = feedDiv.dataset.feedId;
        const header = feedDiv.querySelector('.feed-header');
        
        header.addEventListener('click', async function(e) {
            // Don't expand if clicking on a link or button
            if (e.target.tagName === 'A' || e.target.tagName === 'BUTTON') {
                return;
            }
            const details = feedDiv.querySelector('.feed-details');
            const abstract = details.querySelector('.feed-abstract');
            
            // Toggle expansion
            details.classList.toggle('expanded');
            feedDiv.classList.toggle('expanded');
            
            // Load content if expanding and not already loaded
            if (details.classList.contains('expanded') && !abstract.dataset.loaded) {
                abstract.innerHTML = '<div class="loading">Loading abstract...</div>';
                try {
                    const response = await fetch(`/api/feeds/${feedId}/content`);
                    const data = await response.json();
                    abstract.innerHTML = data.content || 'No abstract available.';
                    abstract.dataset.loaded = 'true';
                } catch (error) {
                    abstract.innerHTML = 'Failed to load abstract.';
                }
            }
        });
    });
}

function displayAcademicResults(results) {
    const container = document.getElementById('searchResults');

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
                    ${paper.venue ? `<strong>${paper.venue}</strong>` : ''}
                    ${paper.authors ? `${paper.venue ? ' • ' : ''}${paper.authors.map(a => typeof a === 'object' ? a.name : a).join(', ')}` : ''}
                    ${(paper.publicationDate || paper.year) ? `${(paper.venue || paper.authors) ? ' • ' : ''}${paper.publicationDate ? new Date(paper.publicationDate).toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: 'numeric' }) : paper.year}` : ''}
                </div>
                <div class="search-result-abstract">
                    ${paper.abstract || 'No abstract available'}
                </div>
                <div class="search-result-actions">
                    ${isAlreadyAdded ?
            '<span class="already-added-badge">✓ Already in database</span>' :
            `<button class="btn btn-add" onclick='addPaperToDatabase(${JSON.stringify(paper).replace(/'/g, "&apos;")}, this)'>
                        ➕ Add to Database
                     </button>`
        }
                    ${paper.url ? `<a href="${paper.url}" target="_blank" class="btn btn-primary">🔗 View Paper</a>` : ''}
                </div>
            </div>
        `;
    }).join('');
}

async function addPaperToDatabase(paper, button) {
    button.disabled = true;
    button.textContent = 'Adding...';

    try {
        const response = await fetch('/api/scholarly-database/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ paper: paper })
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
    const feedsSection = document.getElementById('feedsContainer');
    const resultsSection = document.getElementById('searchResultsContainer');

    feedsSection.style.display = 'block';
    resultsSection.style.display = 'none';

    // Clear URL parameters
    const newUrl = new URL(window.location);
    newUrl.searchParams.delete('q');
    window.history.pushState({}, '', newUrl);
}

function backToFeedList() {
    document.getElementById('generalSearchContainer').style.display = 'none';
    document.getElementById('generalSearchResultsContainer').style.display = 'none';
    document.getElementById('semanticSearchContainer').style.display = 'none';
    document.getElementById('searchResultsContainer').style.display = 'none';
    document.getElementById('feedsContainer').style.display = 'block';

    const newUrl = new URL(window.location);
    newUrl.searchParams.delete('q');
    window.history.pushState({}, '', newUrl);
}

function backToSearchInput() {
    document.getElementById('searchResultsContainer').style.display = 'none';
    document.getElementById('semanticSearchContainer').style.display = 'block';
}

function copySearchLink(event) {
    // Determine which URL to copy
    let url;
    if (currentSearchShortName) {
        // Use the short link if available
        const baseUrl = window.location.origin;
        url = `${baseUrl}/link/${currentSearchShortName}`;
    } else {
        // Fall back to current URL
        url = window.location.href;
    }
    
    // Get the button element
    const btn = event ? event.target : document.querySelector('[onclick*="copySearchLink"]');
    
    // Copy to clipboard
    navigator.clipboard.writeText(url).then(() => {
        // Show success feedback
        const originalText = btn.innerHTML;
        btn.innerHTML = '✓ Copied!';
        btn.disabled = true;
        
        // Reset button after 2 seconds
        setTimeout(() => {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy URL:', err);
        alert('Failed to copy link to clipboard');
    });
}

// Summary generation
async function generateSummary(papers) {
    const summarySection = document.getElementById('searchSummarySection');
    const summaryContent = document.getElementById('searchSummaryContent');
    const summaryInitial = document.getElementById('searchSummaryInitial');
    const summaryLoading = document.getElementById('searchSummaryLoading');
    const summaryText = document.getElementById('searchSummaryText');
    
    if (!summaryContent) return;
    
    // Show the summary section
    summarySection.style.display = 'block';
    summaryInitial.style.display = 'none';
    summaryLoading.style.display = 'block';
    summaryText.innerHTML = '';

    try {
        const response = await fetch('/api/summarize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                feed_ids: papers.slice(0, 10).map(p => p.rowid || p.id)
            })
        });

        if (!response.ok) throw new Error('Summary generation failed');

        const data = await response.json();
        summaryLoading.style.display = 'none';
        summaryText.style.display = 'block';
        summaryText.innerHTML = `
            <div class="summary-text">${data.summary_html || data.summary_markdown || 'No summary available'}</div>
            <div class="summary-disclaimer">
                <p><strong>Note:</strong> This summary was generated by AI and may contain inaccuracies.
                Always refer to the original papers for authoritative information.</p>
            </div>
        `;
    } catch (error) {
        console.error('Summary generation error:', error);
        summaryLoading.style.display = 'none';
        summaryText.style.display = 'block';
        summaryText.innerHTML = '<div class="error">Failed to generate summary</div>';
    }
}

// Helper function to get current search results
let currentSearchResults = [];
let currentSearchShortName = null;

function getCurrentSearchResults() {
    return currentSearchResults;
}

// Poster generation
async function generatePoster(papers) {
    const summarySection = document.getElementById('searchSummarySection');
    const summaryInitial = document.getElementById('searchSummaryInitial');
    const posterLoading = document.getElementById('searchPosterLoading');
    const posterContent = document.getElementById('searchPosterContent');
    
    if (!posterContent) return;
    
    // Show the summary section and poster loading
    summarySection.style.display = 'block';
    summaryInitial.style.display = 'none';
    posterLoading.style.display = 'block';
    posterContent.style.display = 'none';

    try {
        const response = await fetch('/api/generate-poster', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                feed_ids: papers.slice(0, 10).map(p => p.rowid || p.id)
            })
        });

        if (!response.ok) throw new Error('Poster generation failed');

        const data = await response.json();
        const jobId = data.job_id;
        
        // Poll for poster completion
        const checkPosterStatus = async () => {
            try {
                const statusResponse = await fetch(`/api/poster-status/${jobId}`);
                const statusData = await statusResponse.json();
                
                if (statusData.status === 'completed') {
                    posterLoading.style.display = 'none';
                    posterContent.style.display = 'block';
                    
                    // Create a blob URL from the HTML content
                    const blob = new Blob([statusData.poster_html], { type: 'text/html' });
                    const url = URL.createObjectURL(blob);
                    
                    posterContent.innerHTML = `
                        <iframe src="${url}" class="poster-iframe" title="Research Poster"></iframe>
                    `;
                } else if (statusData.status === 'error') {
                    throw new Error(statusData.error || 'Poster generation failed');
                } else {
                    // Still processing, check again in 2 seconds
                    setTimeout(checkPosterStatus, 2000);
                }
            } catch (error) {
                console.error('Poster status check error:', error);
                posterLoading.style.display = 'none';
                posterContent.style.display = 'block';
                posterContent.innerHTML = '<div class="error">Failed to generate poster</div>';
            }
        };
        
        // Start polling
        setTimeout(checkPosterStatus, 2000);
    } catch (error) {
        console.error('Poster generation error:', error);
        posterLoading.style.display = 'none';
        posterContent.style.display = 'block';
        posterContent.innerHTML = '<div class="error">Failed to generate poster</div>';
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    // Initialize from config
    initializeFromConfig();
    
    // Add event handlers for summary buttons
    const generateSummaryBtn = document.getElementById('generateSearchSummaryBtn');
    const generatePosterBtn = document.getElementById('generateSearchPosterBtn');
    
    if (generateSummaryBtn) {
        generateSummaryBtn.addEventListener('click', function() {
            // Get current search results
            const feeds = getCurrentSearchResults();
            if (feeds && feeds.length > 0) {
                generateSummary(feeds);
            }
        });
    }
    
    if (generatePosterBtn) {
        generatePosterBtn.addEventListener('click', function() {
            // Get current search results
            const feeds = getCurrentSearchResults();
            if (feeds && feeds.length > 0) {
                generatePoster(feeds);
            }
        });
    }

    // Check for search query in URL
    const urlParams = new URLSearchParams(window.location.search);
    const searchQuery = urlParams.get('q');

    if (searchQuery) {
        // Restore search from URL
        document.getElementById('generalSearchInput').value = searchQuery;
        performGeneralSearch();
    } else {
        // Load initial feeds
        loadFeeds();
    }

    // Update bookmark button visibility
    updateBookmarkButton();

    // Initialize score filter
    const scoreSlider = document.getElementById('scoreSlider');
    if (scoreSlider) {
        // Find the index of the current min score in the thresholds array
        const thresholdIndex = window.feedsConfig.scoreThresholds.findIndex(t => t === currentMinScore);
        if (thresholdIndex !== -1) {
            scoreSlider.value = thresholdIndex;
            document.getElementById('scoreValue').textContent = window.feedsConfig.scoreLabels[thresholdIndex];
        } else {
            // Default to index 2 (0.25 threshold)
            scoreSlider.value = 2;
            document.getElementById('scoreValue').textContent = window.feedsConfig.scoreLabels[2];
        }
    }
});