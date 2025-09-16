// Similar Articles section script for Paper Details page
// Depends on: common.js (getScoreGradientColor, getSimilarityGradientColor, formatDate, formatAuthors)

window.SimilarSection = (function() {
  let sourceFeedId = null;
  let similarArticles = [];

  function scoreBadgeHTML(score, iconsHtml) {
    const bg = getScoreGradientColor(score);
    const text = score !== null && score !== undefined ? Math.round(score * 100).toString() : 'N/A';
    return `<span class=\"score-badge preference-score\" style=\"background: ${bg}\" title=\"Predicted preference\">${text}${iconsHtml || ''}</span>`;
  }

  function similarityBadgeHTML(similarity) {
    const color = getSimilarityGradientColor(similarity);
    const text = Math.round(similarity * 100).toString();
    return `<span class="similarity-badge score-badge" style="background: ${color}" title="Similarity to selected paper">${text}</span>`;
  }

  function createIcons(feed) {
    const icons = [];
    if (feed.shared) icons.push('<span class="score-icon shared" title="In Queue">📤</span>');
    if (feed.broadcasted) icons.push('<span class="score-icon broadcasted" title="Broadcasted">📡</span>');
    return icons.length > 0 ? `<div class="score-icons">${icons.join('')}</div>` : '';
  }

  function createVoteBadges(feed) {
    const badges = [];
    const pos = feed.positive_votes || 0;
    const neg = feed.negative_votes || 0;
    if (pos > 0) badges.push(`<span class="vote-badge vote-positive" title="${pos} interested">+${pos}</span>`);
    if (neg > 0) badges.push(`<span class="vote-badge vote-negative" title="${neg} not interested">−${neg}</span>`);
    return badges.length > 0 ? `<div class="vote-badges-container">${badges.join('')}</div>` : '';
  }

  function createFeedElement(feed) {
    const iconsHtml = createIcons(feed);
    return `
      <div class="feed-item" data-feed-rowid="${feed.rowid}" data-positive-votes="${feed.positive_votes || 0}" data-negative-votes="${feed.negative_votes || 0}">
        <div class="feed-header">
          <div class="badges-container">
            ${scoreBadgeHTML(feed.score, iconsHtml)}
            ${similarityBadgeHTML(feed.similarity)}
          </div>
          <div class="feed-content">
            <h3 class="feed-title">${feed.title}</h3>
            <div class="feed-meta">
              <div class="feed-meta-item feed-origin">${feed.origin || 'Unknown Source'}</div>
              ${feed.author ? `<div class="feed-meta-item feed-author" title="${feed.author}">${formatAuthors(feed.author)}</div>` : ''}
              <div class="feed-meta-item feed-date">${formatDate(feed.published || feed.added)}</div>
            </div>
          </div>
          ${createVoteBadges(feed)}
        </div>
        <div class="feed-details">
          <div class="feed-abstract">Click to load abstract...</div>
          <div class="feed-actions">
            <button class="btn btn-details" onclick="window.location.href='/paper/${feed.rowid}'">📄<span class="btn-text"> Details</span></button>
            ${feed.link ? `<a href="${feed.link}" target="_blank" class="btn btn-open-article">📄<span class="btn-text">Open Article</span></a>` : ''}
            <button class="btn btn-share ${feed.shared ? 'shared' : ''} ${feed.broadcasted ? 'disabled' : ''}"
                    onclick="SimilarSection.shareFeed(${feed.rowid}, this, ${feed.broadcasted})"
                    data-shared="${feed.shared ? 'true' : 'false'}" ${feed.broadcasted ? 'disabled title=\"Already broadcasted\"' : ''}>
              ${feed.broadcasted ? '📡' : '📤'}<span class="btn-text"> ${feed.broadcasted ? 'Broadcasted' : (feed.shared ? 'Shared' : 'Share')}</span>
            </button>
            <button class="btn btn-thumbs-up ${feed.label === 1 ? 'active' : ''}" onclick="SimilarSection.feedbackFeed(${feed.rowid}, 1, this)" data-label="${feed.label}">👍<span class="btn-text"> Interested</span></button>
            <button class="btn btn-thumbs-down ${feed.label === 0 ? 'active' : ''}" onclick="SimilarSection.feedbackFeed(${feed.rowid}, 0, this)" data-label="${feed.label}">👎<span class="btn-text"> Not Interested</span></button>
          </div>
        </div>
      </div>`;
  }

  function loadFeedContent(feedRowid, detailsElement) {
    fetch(`/api/feeds/${feedRowid}/content`)
      .then(r => r.json())
      .then(data => {
        const el = detailsElement.querySelector('.feed-abstract');
        el.textContent = data.content || data.tldr || 'No content available';
      })
      .catch(() => {
        const el = detailsElement.querySelector('.feed-abstract');
        el.textContent = 'Error loading content';
        el.style.color = 'var(--feedback-error-title-color)';
      });
  }

  function bindExpansion() {
    const container = document.getElementById('similar-section');
    if (!container) return;
    container.addEventListener('click', function(e) {
      if (e.target.closest('button') || e.target.closest('a')) return;
      const feedItem = e.target.closest('.feed-item');
      if (!feedItem) return;
      const details = feedItem.querySelector('.feed-details');
      const authorEl = feedItem.querySelector('.feed-author');
      const expanded = feedItem.classList.contains('expanded');
      if (expanded) {
        feedItem.classList.remove('expanded');
        details.classList.remove('expanded');
        if (authorEl && authorEl.dataset.fullAuthor) {
          authorEl.textContent = formatAuthors(authorEl.dataset.fullAuthor);
        }
      } else {
        feedItem.classList.add('expanded');
        details.classList.add('expanded');
        if (authorEl && authorEl.title) {
          authorEl.dataset.fullAuthor = authorEl.title;
          authorEl.textContent = authorEl.title;
        }
        const abs = details.querySelector('.feed-abstract');
        if (abs && (abs.textContent === 'Click to load abstract...' || abs.textContent === 'Loading content...')) {
          abs.textContent = 'Loading content...';
          loadFeedContent(feedItem.dataset.feedRowid, details);
        }
      }
    });
  }

  function loadSimilarFeeds() {
    fetch(`/api/feeds/${sourceFeedId}/similar`)
      .then(r => r.json())
      .then(data => {
        similarArticles = data.similar_feeds || [];
        const list = document.getElementById('similarFeedsList');
        list.innerHTML = '';
        if (similarArticles.length > 0) {
          similarArticles.forEach(feed => list.insertAdjacentHTML('beforeend', createFeedElement(feed)));
          document.getElementById('similarLoading').style.display = 'none';
        } else {
          document.getElementById('similarLoading').innerHTML = '<div style="padding:20px; text-align:center; color: var(--text-meta);">No similar articles found</div>';
        }
      })
      .catch(err => {
        console.error('Error loading similar:', err);
        document.getElementById('similarLoading').innerHTML = '<div style="padding:20px; text-align:center; color: var(--feedback-error-title-color);">Error loading similar papers</div>';
      });
  }

  // Interactions
  async function shareFeed(e, feedRowid, buttonElement, isBroadcasted) {
    if (e) e.stopPropagation();
    if (isBroadcasted) return;
    const isShared = buttonElement.dataset.shared === 'true';
    try {
      const res = await fetch(`/api/feeds/${feedRowid}/share`, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({action: 'toggle'}) });
      const data = await res.json();
      if (!data.success) throw new Error(data.error || 'Unknown');
      // Update button label/state
      if (data.action === 'share') {
        buttonElement.dataset.shared = 'true';
        buttonElement.innerHTML = '📤<span class="btn-text"> Shared</span>';
        buttonElement.classList.add('shared');
        // add icon to score badge
        const feedItem = buttonElement.closest('.feed-item');
        const scoreBadge = feedItem.querySelector('.badges-container .preference-score');
        if (scoreBadge && !scoreBadge.querySelector('.score-icons')) {
          scoreBadge.insertAdjacentHTML('beforeend', '<div class="score-icons"><span class="score-icon shared" title="In Queue">📤</span></div>');
        }
      } else {
        buttonElement.dataset.shared = 'false';
        buttonElement.innerHTML = '📤<span class="btn-text"> Share</span>';
        buttonElement.classList.remove('shared');
        const feedItem = buttonElement.closest('.feed-item');
        const icon = feedItem.querySelector('.score-icon.shared');
        if (icon) icon.remove();
      }
    } catch (e) {
      console.error('Share failed:', e);
      buttonElement.innerHTML = isShared ? '📤<span class="btn-text"> Shared</span>' : '📤<span class="btn-text"> Share</span>';
      alert('Failed to update share. Please try again.');
    }
  }

  async function feedbackFeed(e, feedRowid, score, buttonElement) {
    if (e) e.stopPropagation();
    const currentLabel = parseFloat(buttonElement.dataset.label);
    const isRemoving = currentLabel === score;
    buttonElement.disabled = true;
    const other = score === 1 ? buttonElement.nextElementSibling : buttonElement.previousElementSibling;
    if (other) other.disabled = true;
    try {
      const res = await fetch(`/api/feeds/${feedRowid}/feedback`, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ score: isRemoving ? null : score }) });
      const data = await res.json();
      if (!data.success) throw new Error(data.error || 'Unknown');
      if (isRemoving) {
        buttonElement.classList.remove('active');
        buttonElement.dataset.label = '';
      } else {
        buttonElement.classList.add('active');
        buttonElement.dataset.label = score;
        if (other) { other.classList.remove('active'); other.dataset.label = ''; }
      }
      // update counts UI
      const feedItem = buttonElement.closest('.feed-item');
      let badgesDiv = feedItem.querySelector('.vote-badges-container');
      let pos = parseInt(feedItem.dataset.positiveVotes) || 0;
      let neg = parseInt(feedItem.dataset.negativeVotes) || 0;
      if (isRemoving) {
        if (score === 1) pos = Math.max(0, pos - 1); else neg = Math.max(0, neg - 1);
      } else {
        const prev = parseFloat(other?.dataset.label);
        if (prev === 1 && score === 0) { pos = Math.max(0, pos - 1); neg++; }
        else if (prev === 0 && score === 1) { neg = Math.max(0, neg - 1); pos++; }
        else if (score === 1) pos++; else neg++;
      }
      if (!badgesDiv && (pos > 0 || neg > 0)) {
        feedItem.querySelector('.feed-header').insertAdjacentHTML('beforeend', '<div class="vote-badges-container"></div>');
        badgesDiv = feedItem.querySelector('.vote-badges-container');
      }
      const exPos = badgesDiv ? badgesDiv.querySelector('.vote-positive') : null;
      const exNeg = badgesDiv ? badgesDiv.querySelector('.vote-negative') : null;
      if (pos > 0) { if (exPos) exPos.textContent = `+${pos}`; else if (badgesDiv) badgesDiv.insertAdjacentHTML('beforeend', `<span class="vote-badge vote-positive">+${pos}</span>`); }
      else if (exPos) exPos.remove();
      if (neg > 0) { if (exNeg) exNeg.textContent = `−${neg}`; else if (badgesDiv) badgesDiv.insertAdjacentHTML('beforeend', `<span class="vote-badge vote-negative">−${neg}</span>`); }
      else if (exNeg) exNeg.remove();
      if (badgesDiv && badgesDiv.children.length === 0) badgesDiv.remove();
      feedItem.dataset.positiveVotes = pos; feedItem.dataset.negativeVotes = neg;
    } catch (e) {
      console.error('Feedback failed:', e);
      alert('Failed to update feedback. Please try again.');
    } finally {
      buttonElement.disabled = false; if (other) other.disabled = false;
    }
  }

  // Summary
  function revealSummarySection() {
    const section = document.getElementById('similarSummarySection');
    if (section) section.style.display = 'block';
  }

  function bindSummary() {
    const genBtn = document.getElementById('similarGenerateSummaryBtn');
    const posterBtn = document.getElementById('similarGeneratePosterBtn');
    if (genBtn) genBtn.addEventListener('click', () => generateSummary());
    if (posterBtn) posterBtn.addEventListener('click', () => generatePoster());
  }

  function generateSummary() {
    const initial = document.getElementById('similarSummaryInitial');
    const loading = document.getElementById('similarSummaryLoading');
    const text = document.getElementById('similarSummaryText');
    const ids = [sourceFeedId, ...similarArticles.map(a => a.rowid)];
    revealSummarySection();
    if (initial) initial.style.display = 'none';
    if (loading) loading.style.display = 'block';
    if (text) { text.style.display = 'none'; text.innerHTML = ''; }
    fetch('/api/summarize', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ feed_ids: ids }) })
      .then(r => r.json()).then(data => {
        if (loading) loading.style.display = 'none';
        if (text) text.style.display = 'block';
        if (data.success) {
          if (text) text.innerHTML = `<div class="summary-text">${data.summary_html || data.summary_markdown || 'No summary available'}</div>
            <div class="summary-disclaimer"><p><strong>Note:</strong> This summary was generated by AI and may contain inaccuracies. Please refer to the original articles for full details.</p></div>`;
        } else {
          if (text) text.innerHTML = '<div class="error">Failed to generate summary</div>';
        }
      }).catch(() => {
        if (loading) loading.style.display = 'none';
        if (text) { text.style.display = 'block'; text.innerHTML = '<div class="error">Failed to generate summary</div>'; }
      });
  }

  function generatePoster() {
    const initial = document.getElementById('similarSummaryInitial');
    const loading = document.getElementById('similarPosterLoading');
    const content = document.getElementById('similarPosterContent');
    const text = document.getElementById('similarSummaryText');
    const ids = [sourceFeedId, ...similarArticles.map(a => a.rowid)];
    revealSummarySection();
    if (initial) initial.style.display = 'none';
    if (loading) loading.style.display = 'block';
    if (content) content.style.display = 'none';
    if (text) text.style.display = 'none';
    fetch('/api/generate-poster', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ feed_ids: ids }) })
      .then(r => r.json()).then(data => {
        const jobId = data.job_id; if (!jobId) throw new Error('No job');
        const poll = setInterval(() => {
          fetch(`/api/poster-status/${jobId}`).then(r => r.json()).then(s => {
            if (s.status === 'completed') {
              clearInterval(poll); if (loading) loading.style.display = 'none';
              if (content) {
                content.innerHTML = `
                <div class="poster-actions"><button class="btn btn-primary-soft btn-print" onclick="SimilarSection.printPoster()">🖨️ Print</button></div>
                <iframe id="similarPosterFrame" class="poster-iframe" srcdoc="${(s.poster_html || '').replace(/"/g, '&quot;')}" frameborder="0"></iframe>
                <div class="summary-disclaimer"><p><strong>Note:</strong> This AI-generated infographic is based on titles/abstracts and may contain inaccuracies.</p></div>`;
                content.style.display = 'block';
              }
            } else if (s.status === 'error') {
              clearInterval(poll);
              if (loading) loading.style.display = 'none';
              if (content) {
                content.innerHTML = `<p style="color: var(--feedback-error-title-color);">Failed to generate poster${s.error ? `: ${s.error}` : ''}</p>`;
                content.style.display = 'block';
              }
              if (initial) initial.style.display = 'flex';
            }
          }).catch(() => {
            clearInterval(poll);
            if (loading) loading.style.display = 'none';
            if (content) {
              content.innerHTML = `<p style="color: var(--feedback-error-title-color);">An error occurred while checking job status.</p>`;
              content.style.display = 'block';
            }
            if (initial) initial.style.display = 'flex';
          });
        }, 3000);
        setTimeout(() => {
          clearInterval(poll);
          if (loading && loading.style.display !== 'none') {
            loading.style.display = 'none';
            if (content) {
              content.innerHTML = `<p style=\"color: var(--feedback-error-title-color);\">Generation timed out. Please try again.</p>`;
              content.style.display = 'block';
            }
            if (initial) initial.style.display = 'flex';
          }
        }, 300000);
      }).catch(() => {
        if (loading) loading.style.display = 'none';
        if (content) {
          content.innerHTML = `<p style="color: var(--feedback-error-title-color);">An error occurred while generating the poster.</p>`;
          content.style.display = 'block';
        }
        if (initial) initial.style.display = 'flex';
      });
  }

  function printPoster() {
    const iframe = document.getElementById('similarPosterFrame');
    if (iframe && iframe.contentWindow) { iframe.contentWindow.focus(); iframe.contentWindow.print(); }
  }

  function init(opts) {
    sourceFeedId = opts.sourceFeedId;
    bindExpansion();
    bindSummary();
    loadSimilarFeeds();
    // Scroll to section if anchor present
    if (window.location.hash === '#similar') {
      const sec = document.getElementById('similar-section');
      if (sec) sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  return { init, shareFeed, feedbackFeed, printPoster };
})();
