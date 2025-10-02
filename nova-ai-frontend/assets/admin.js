(function ($) {
  'use strict';

  const NovaAIAdmin = {
    apiBase: (window.novaAIAdmin && window.novaAIAdmin.apiBase) || 'https://api.ailinux.me:9000',
    ajaxUrl: window.novaAIAdmin && window.novaAIAdmin.ajaxUrl,
    nonce: window.novaAIAdmin && window.novaAIAdmin.nonce,
    state: {
      health: null,
      status: null,
      metrics: null,
      models: [],
      mcp: null,
      config: null,
      lastUpdated: null,
      poll: { timer: null, base: 15000, max: 60000, failures: 0 },
    },

    init() {
      this.bindEvents();

      if ($('.nova-ai-dashboard').length) {
        this.refreshDashboard();
        this.loadRecentPosts();
        this.postsTimer = window.setInterval(() => this.loadRecentPosts(), 60000);
      }

      if ($('#nova-crawler-jobs-container').length) {
        this.loadCrawlerJobs();
        this.jobsTimer = window.setInterval(() => this.loadCrawlerJobs(), 15000);
      }
    },

    bindEvents() {
      const settingsForm = $('#nova-crawler-settings form');
      if (settingsForm.length) {
        settingsForm.on('submit', (event) => {
          event.preventDefault();
          this.submitSettings();
        });
      }

      $('.nova-control-btn').on('click', (event) => this.handleControlClick(event));
      $('#nova-trigger-publish').on('click', () => this.triggerPublish());
    },

    scheduleDashboardRefresh(delay = this.state.poll.base) {
      this.clearDashboardTimer();
      this.state.poll.timer = window.setTimeout(() => this.refreshDashboard(), delay);
    },

    clearDashboardTimer() {
      if (this.state.poll.timer) {
        window.clearTimeout(this.state.poll.timer);
        this.state.poll.timer = null;
      }
    },

    async refreshDashboard() {
      this.clearDashboardTimer();
      try {
        const [health, status, metrics] = await Promise.all([
          this.fetchRequired('/health'),
          this.fetchRequired('/admin/crawler/status'),
          this.fetchRequired('/admin/crawler/metrics'),
        ]);

        const [models, config, mcp] = await Promise.all([
          this.fetchOptional('/v1/models'),
          this.fetchOptional('/admin/crawler/config'),
          this.fetchOptional('/mcp/status'),
        ]);

        this.state.health = health;
        this.state.status = status;
        this.state.metrics = metrics;
        this.state.models = Array.isArray(models?.data)
          ? models.data
          : Array.isArray(models)
            ? models
            : [];
        this.state.config = config || this.state.config;
        this.state.mcp = mcp || this.state.mcp;
        this.state.lastUpdated = new Date();
        this.state.poll.failures = 0;

        this.renderDashboard();
        this.scheduleDashboardRefresh(this.state.poll.base);
      } catch (error) {
        this.handleDashboardError(error);
      }
    },

    async fetchRequired(endpoint, options = {}) {
      return this.fetchAPI(endpoint, options);
    },

    async fetchOptional(endpoint, options = {}) {
      try {
        return await this.fetchAPI(endpoint, options);
      } catch (error) {
        console.warn('[NovaAI][Optional Fetch]', endpoint, error);
        return null;
      }
    },

    handleDashboardError(error) {
      console.error('[NovaAI][Dashboard]', error);
      this.state.poll.failures += 1;
      const delay = Math.min(
        this.state.poll.base * Math.pow(2, this.state.poll.failures - 1),
        this.state.poll.max
      );
      const message = error && error.status === 429
        ? 'Rate Limit erreicht – bitte kurz warten.'
        : 'Backend nicht erreichbar — prüfe API-Basis-URL.';
      this.setAlert(message);
      $('#nova-settings-message').text(message);
      this.scheduleDashboardRefresh(delay);
    },

    setAlert(message) {
      const $alert = $('#nova-dashboard-alert');
      if (!$alert.length) {
        return;
      }

      if (!message) {
        $alert.attr('hidden', true).removeClass('is-visible').text('');
        return;
      }

      $alert.text(message).removeAttr('hidden').addClass('is-visible');
    },

    renderDashboard() {
      this.setAlert(null);
      $('#nova-settings-message').text('');
      this.renderBackendServices();
      this.renderSettingsPanel();
      this.renderModelsPanel();
    },

    renderBackendServices() {
      const status = this.state.status || {};
      const metrics = this.state.metrics || {};
      const overview = metrics.overview || {};
      const queueDepth = metrics.queue_depth?.total
        ?? status.main_manager?.summary?.queue_depth
        ?? 0;
      const userErrorRate = metrics.user_crawler?.error_rate ?? null;
      const autoErrorRate = metrics.auto_crawler?.error_rate ?? null;

      const userSummary = status.user_crawler?.summary || {};
      const autoSummary = status.auto_crawler?.summary || {};
      const publisherSummary = status.auto_publisher?.summary || {};
      const managerSummary = status.main_manager?.summary || {};

      const postsToday = overview.posts_today ?? metrics.posts_today ?? '—';

      this.setStatBadge('#nova-publisher-status', publisherSummary);
      this.setCrawlerBadge('#nova-crawler-status', userSummary, autoSummary);
      $('#nova-posts-today').text(this.formatNumber(postsToday));
      $('#nova-pending-results').text(this.formatNumber(queueDepth));

      this.updateServiceCard('api', {
        running: this.state.health?.status === 'ok',
        last_heartbeat: this.state.lastUpdated ? this.state.lastUpdated.toISOString() : null,
      }, [
        `Status: <strong>${this.state.health?.status || 'unknown'}</strong>`,
        `Modelle: <strong>${this.state.models.length}</strong>`,
        this.state.lastUpdated
          ? `Stand: <strong>${this.state.lastUpdated.toLocaleTimeString()}</strong>`
          : null,
      ]);

      this.updateServiceCard('user', userSummary, [
        `Worker: <strong>${this.formatNumber(userSummary.workers)}</strong>`,
        `Aktive Jobs: <strong>${this.formatNumber(userSummary.active_jobs)}</strong>`,
        `Queue: <strong>${this.formatNumber(userSummary.queue_depth)}</strong>`,
        userErrorRate !== null
          ? `Fehlerquote: <strong>${this.formatPercent(userErrorRate)}</strong>`
          : null,
        userSummary.last_heartbeat
          ? `Heartbeat: <strong>${this.formatTimestamp(userSummary.last_heartbeat)}</strong>`
          : null,
      ]);

      this.updateServiceCard('auto', autoSummary, [
        `Worker: <strong>${this.formatNumber(autoSummary.workers)}</strong>`,
        `Aktive Jobs: <strong>${this.formatNumber(autoSummary.active_jobs)}</strong>`,
        `Queue: <strong>${this.formatNumber(autoSummary.queue_depth)}</strong>`,
        autoErrorRate !== null
          ? `Fehlerquote: <strong>${this.formatPercent(autoErrorRate)}</strong>`
          : null,
        autoSummary.last_heartbeat
          ? `Heartbeat: <strong>${this.formatTimestamp(autoSummary.last_heartbeat)}</strong>`
          : null,
      ]);

      this.updateServiceCard('publisher', publisherSummary, [
        `Status: <strong>${publisherSummary.running ? 'Aktiv' : 'Gestoppt'}</strong>`,
        publisherSummary.last_heartbeat
          ? `Letzte Ausführung: <strong>${this.formatTimestamp(publisherSummary.last_heartbeat)}</strong>`
          : null,
      ]);

      this.updateServiceCard('manager', managerSummary, [
        `Worker aktiv: <strong>${this.formatNumber(managerSummary.workers)}</strong>`,
        `Aktive Jobs: <strong>${this.formatNumber(managerSummary.active_jobs)}</strong>`,
        `Queue: <strong>${this.formatNumber(managerSummary.queue_depth)}</strong>`,
        managerSummary.last_heartbeat
          ? `Heartbeat: <strong>${this.formatTimestamp(managerSummary.last_heartbeat)}</strong>`
          : null,
      ]);
    },

    setStatBadge(selector, summary) {
      const $el = $(selector);
      if (!$el.length) {
        return;
      }

      if (!summary || typeof summary.running === 'undefined') {
        $el.html(this.createBadge('—', 'pending'));
        return;
      }

      const label = summary.running ? 'Aktiv' : 'Gestoppt';
      const tone = summary.running ? 'ok' : 'err';
      const heartbeat = summary.last_heartbeat
        ? `<div class="nova-meta-inline">${this.formatTimestamp(summary.last_heartbeat)}</div>`
        : '';

      $el.html(`${this.createBadge(label, tone)}${heartbeat}`);
    },

    setCrawlerBadge(selector, userSummary, autoSummary) {
      const $el = $(selector);
      if (!$el.length) {
        return;
      }

      const userBadge = this.createBadge(
        userSummary && typeof userSummary.running !== 'undefined'
          ? (userSummary.running ? 'User Aktiv' : 'User Gestoppt')
          : 'User —',
        this.toneFromSummary(userSummary)
      );

      const autoBadge = this.createBadge(
        autoSummary && typeof autoSummary.running !== 'undefined'
          ? (autoSummary.running ? 'Auto Aktiv' : 'Auto Gestoppt')
          : 'Auto —',
        this.toneFromSummary(autoSummary)
      );

      $el.html(`<div class="nova-status-badges">${userBadge}${autoBadge}</div>`);
    },

    updateServiceCard(name, summary, metaLines) {
      const badgeEl = $(`#nova-service-badge-${name}`);
      const metaEl = $(`#nova-service-meta-${name}`);
      if (!badgeEl.length || !metaEl.length) {
        return;
      }

      const tone = this.toneFromSummary(summary);
      const label = summary && typeof summary.running !== 'undefined'
        ? (summary.running ? 'Aktiv' : 'Gestoppt')
        : '—';

      badgeEl.html(this.createBadge(label, tone));

      const lines = (metaLines || []).filter(Boolean).map((line) => `<span>${line}</span>`);
      metaEl.html(lines.join(''));
    },

    toneFromSummary(summary) {
      if (!summary || typeof summary.running === 'undefined') {
        return 'pending';
      }
      return summary.running ? 'ok' : 'err';
    },

    createBadge(label, tone) {
      let cls = 'nova-badge nova-badge--pending';
      if (tone === 'ok') {
        cls = 'nova-badge nova-badge--ok';
      } else if (tone === 'warn') {
        cls = 'nova-badge nova-badge--warn';
      } else if (tone === 'err') {
        cls = 'nova-badge nova-badge--err';
      } else if (tone === 'info') {
        cls = 'nova-badge nova-badge--info';
      }
      return `<span class="${cls}">${label}</span>`;
    },

    renderSettingsPanel() {
      const config = this.state.config;
      const $form = $('#nova-crawler-settings form');
      if (!$form.length || !config) {
        return;
      }

      $('#nova-setting-user-workers').val(config.user_crawler_workers);
      $('#nova-setting-user-concurrency').val(config.user_crawler_max_concurrent);
      $('#nova-setting-auto-enabled').prop('checked', !!config.auto_crawler_enabled);
      $('#nova-setting-auto-workers').val(config.auto_crawler_workers);
      $('#nova-setting-flush').val(config.crawler_flush_interval);
      $('#nova-setting-retention').val(config.crawler_retention_days);
      $('#nova-settings-status').text('');
    },

    async submitSettings() {
      const config = this.state.config || {};
      const $status = $('#nova-settings-status');
      const $button = $('#nova-crawler-settings .btn-save');
      const desired = {
        user_crawler_workers: parseInt($('#nova-setting-user-workers').val(), 10),
        user_crawler_max_concurrent: parseInt($('#nova-setting-user-concurrency').val(), 10),
        auto_crawler_enabled: $('#nova-setting-auto-enabled').is(':checked'),
      };

      const payload = {};
      Object.entries(desired).forEach(([key, value]) => {
        if (typeof value === 'number' && Number.isFinite(value) && config[key] !== value) {
          payload[key] = value;
        }
        if (typeof value === 'boolean' && config[key] !== value) {
          payload[key] = value;
        }
      });

      if (!Object.keys(payload).length) {
        $status.text('Keine Änderungen.');
        return;
      }

      try {
        $button.prop('disabled', true).text('Speichere …');
        $status.text('Übernehme Änderungen …');
        const response = await this.fetchAPI('/admin/crawler/config', {
          method: 'POST',
          body: JSON.stringify(payload),
        });

        if (response && response.config) {
          this.state.config = response.config;
          $status.text('Einstellungen aktualisiert.');
          this.refreshDashboard();
        } else {
          throw new Error('Unerwartete Antwort');
        }
      } catch (error) {
        console.error('[NovaAI][Settings]', error);
        $status.text(`Fehler: ${error.message || error}`);
      } finally {
        $button.prop('disabled', false).text('Save changes');
      }
    },

    async handleControlClick(event) {
      event.preventDefault();
      const $button = $(event.currentTarget);
      const instance = $button.data('instance');
      const action = $button.data('action');
      const $status = $('#nova-control-status');

      try {
        $button.prop('disabled', true);
        $status.text(`Sende ${action} → ${instance} …`);
        const payload = { action, instance };
        await this.fetchAPI('/admin/crawler/control', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        $status.text(`Befehl ${action} für ${instance} ausgeführt.`);
        this.refreshDashboard();
      } catch (error) {
        console.error('[NovaAI][Control]', error);
        const message = error.status === 429
          ? 'Rate Limit erreicht – bitte erneut versuchen.'
          : `Fehler: ${error.message || error}`;
        $status.text(message);
      } finally {
        $button.prop('disabled', false);
      }
    },

    renderModelsPanel() {
      const $list = $('#nova-models-list');
      if (!$list.length) {
        return;
      }

      if (!this.state.models.length) {
        $list.html('<li>Keine Modelle gefunden.</li>');
      } else {
        const items = this.state.models.map((model) => {
          const capabilities = Array.isArray(model.capabilities)
            ? model.capabilities.join(', ')
            : '—';
          return `
            <li>
              <span class="model-id"><strong>${model.id}</strong> (${model.provider})</span>
              <span class="model-capabilities">${capabilities}</span>
            </li>
          `;
        });
        $list.html(items.join(''));
      }

      const $badge = $('#nova-mcp-status');
      if ($badge.length) {
        const mcpStatus = this.state.mcp?.status || 'unknown';
        const tone = mcpStatus === 'ok' ? 'ok' : mcpStatus === 'degraded' ? 'warn' : 'err';
        $badge.html(this.createBadge(mcpStatus.toUpperCase(), tone));
      }
    },

    async loadRecentPosts() {
      const $tbody = $('#nova-recent-posts-tbody');
      if (!$tbody.length || !this.ajaxUrl) {
        return;
      }

      $.post(
        this.ajaxUrl,
        {
          action: 'nova_ai_get_stats',
          nonce: this.nonce,
        },
        (response) => {
          if (!response || !response.success) {
            $tbody.html('<tr><td colspan="5" style="text-align:center;">Fehler beim Laden.</td></tr>');
            return;
          }

          const posts = response.data.recent_posts || [];
          if (!posts.length) {
            $tbody.html('<tr><td colspan="5" style="text-align:center;">Keine Posts</td></tr>');
            return;
          }

          const rows = posts.map((post) => `
            <tr>
              <td><strong>${this.escapeHtml(post.title)}</strong></td>
              <td>—</td>
              <td>Auto-Crawler</td>
              <td>${new Date(post.date).toLocaleString()}</td>
              <td>
                <a href="${post.url}" target="_blank" class="button button-small">Ansehen</a>
              </td>
            </tr>
          `);
          $tbody.html(rows.join(''));
        }
      ).fail(() => {
        $tbody.html('<tr><td colspan="5" style="text-align:center;">WordPress AJAX Fehler</td></tr>');
      });
    },

    async loadCrawlerJobs() {
      const $container = $('#nova-crawler-jobs-container');
      if (!$container.length) {
        return;
      }

      try {
        const jobs = await this.fetchAPI('/v1/crawler/jobs');
        if (!jobs || !jobs.length) {
          $container.html('<p>Keine Crawl-Jobs gefunden.</p>');
          return;
        }

        const rows = jobs.map((job) => `
          <tr>
            <td><code>${job.id}</code></td>
            <td>${(job.seeds || [])[0] || '—'}</td>
            <td><span class="status-badge ${job.status}">${job.status}</span></td>
            <td>${job.pages_crawled || 0} / ${job.max_pages}</td>
            <td>${job.results?.length || 0}</td>
            <td>${job.created_at ? new Date(job.created_at).toLocaleString() : '—'}</td>
          </tr>
        `);

        const table = `
          <table class="wp-list-table widefat fixed striped">
            <thead>
              <tr>
                <th>ID</th>
                <th>Seed</th>
                <th>Status</th>
                <th>Seiten</th>
                <th>Ergebnisse</th>
                <th>Erstellt</th>
              </tr>
            </thead>
            <tbody>${rows.join('')}</tbody>
          </table>
        `;
        $container.html(table);
      } catch (error) {
        console.error('[NovaAI][CrawlerJobs]', error);
        $container.html('<p>Fehler beim Laden der Crawl-Jobs.</p>');
      }
    },

    async triggerPublish() {
      const $button = $('#nova-trigger-publish');
      const $result = $('#nova-trigger-result');
      if (!$button.length) {
        return;
      }

      $button.prop('disabled', true).text('Wird ausgeführt …');
      $result.empty();

      try {
        const response = await $.post(this.ajaxUrl, {
          action: 'nova_ai_trigger_publish',
          nonce: this.nonce,
        });

        if (response.success) {
          $result.html(`<div class="notice notice-success"><p>${response.data.message}</p></div>`);
          this.loadRecentPosts();
        } else {
          $result.html(`<div class="notice notice-error"><p>Fehler: ${response.data}</p></div>`);
        }
      } catch (error) {
        $result.html(`<div class="notice notice-error"><p>Fehler: ${error.message}</p></div>`);
      } finally {
        $button.prop('disabled', false).text('Jetzt veröffentlichen');
      }
    },

    async fetchAPI(endpoint, options = {}) {
      const url = this.apiBase.replace(/\/$/, '') + endpoint;
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), options.timeout || 20000);

      const requestOptions = {
        method: options.method || 'GET',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
          'X-AILinux-Client': 'nova-ai-admin/1.0',
          ...(options.headers || {}),
        },
        signal: controller.signal,
      };

      if (options.body) {
        requestOptions.body = options.body;
      }

      try {
        const response = await fetch(url, requestOptions);
        window.clearTimeout(timeout);

        if (response.status === 204) {
          return null;
        }

        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          const error = new Error(payload.error?.message || `HTTP ${response.status}`);
          error.status = response.status;
          error.endpoint = endpoint;
          throw error;
        }

        return response.json();
      } catch (error) {
        window.clearTimeout(timeout);
        if (error.name === 'AbortError') {
          const timeoutError = new Error('Timeout');
          timeoutError.status = 504;
          timeoutError.endpoint = endpoint;
          throw timeoutError;
        }
        throw error;
      }
    },

    formatNumber(value) {
      if (value === null || value === undefined || Number.isNaN(value)) {
        return '—';
      }
      if (typeof value === 'number') {
        return new Intl.NumberFormat().format(value);
      }
      return String(value);
    },

    formatPercent(value) {
      if (value === null || value === undefined || Number.isNaN(value)) {
        return '—';
      }
      return `${(value * 100).toFixed(1)}%`;
    },

    formatTimestamp(value) {
      try {
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
          return '—';
        }
        return date.toLocaleString();
      } catch (error) {
        return '—';
      }
    },

    escapeHtml(value) {
      return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    },
  };

  $(document).ready(() => NovaAIAdmin.init());
  window.NovaAIAdmin = NovaAIAdmin;
  window.NovaAIAdminTest = {
    forceRefresh: () => NovaAIAdmin.refreshDashboard(),
    state: NovaAIAdmin.state,
  };
})(jQuery);
