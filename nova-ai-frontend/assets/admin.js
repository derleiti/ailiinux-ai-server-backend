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
      config: null,
      lastUpdated: null,
    },

    init() {
      this.bindEvents();

      if ($('#nova-crawler-jobs-container').length) {
        this.loadCrawlerJobs();
        setInterval(() => this.loadCrawlerJobs(), 10000);
      }

      if ($('.nova-ai-dashboard').length) {
        this.setupDashboardShell();
        this.refreshDashboard();
        setInterval(() => this.refreshDashboard(), 30000);
      }
    },

    bindEvents() {
      $('#nova-trigger-publish').on('click', () => this.triggerPublish());
    },

    /* ---------------------------------- */
    /* Dashboard                          */
    /* ---------------------------------- */

    setupDashboardShell() {
      const $dashboard = $('.nova-ai-dashboard');
      if (!$dashboard.length) {
        return;
      }

      if (!$('#nova-backend-services').length) {
        const servicesCard = `
          <section id="nova-backend-services" class="nova-card">
            <div class="nova-card-header">
              <h2>Backend Services</h2>
              <span class="brumo-icon" title="Brumo approves">🐾</span>
            </div>
            <div class="nova-service-grid"></div>
          </section>
        `;
        $dashboard.prepend(servicesCard);
      }

      if (!$('#nova-crawler-settings').length) {
        const settingsCard = `
          <section id="nova-crawler-settings" class="nova-card">
            <div class="nova-card-header">
              <h2>Crawler Settings</h2>
              <span class="nova-inline-warning" id="nova-settings-message"></span>
            </div>
            <form class="nova-settings" novalidate>
              <fieldset>
                <legend>User Crawler</legend>
                <div class="setting-row">
                  <label for="nova-setting-user-workers">Workers</label>
                  <input type="number" id="nova-setting-user-workers" min="1" step="1" data-field="user_crawler_workers" />
                  <p class="setting-help">Dedicated workers for user-initiated crawl jobs.</p>
                </div>
                <div class="setting-row">
                  <label for="nova-setting-user-concurrency">Max Concurrent Pages</label>
                  <input type="number" id="nova-setting-user-concurrency" min="1" step="1" data-field="user_crawler_max_concurrent" />
                  <p class="setting-help">Upper bound of parallel pages fetched by the fast user crawler.</p>
                </div>
              </fieldset>

              <fieldset>
                <legend>Auto Crawler</legend>
                <div class="setting-row">
                  <label class="toggle-label" for="nova-setting-auto-enabled">
                    <input type="checkbox" id="nova-setting-auto-enabled" data-field="auto_crawler_enabled" />
                    <span>Auto crawler enabled</span>
                  </label>
                  <p class="setting-help">Toggle the 24/7 background crawler. Disabling stops all category loops.</p>
                </div>
                <div class="setting-row">
                  <label>Configured Workers</label>
                  <input type="number" id="nova-setting-auto-workers" data-field="auto_crawler_workers" disabled />
                </div>
              </fieldset>

              <fieldset>
                <legend>Retention &amp; Flush</legend>
                <div class="setting-row">
                  <label>Flush Interval (seconds)</label>
                  <input type="number" id="nova-setting-flush" data-field="crawler_flush_interval" disabled />
                </div>
                <div class="setting-row">
                  <label>Retention (days)</label>
                  <input type="number" id="nova-setting-retention" data-field="crawler_retention_days" disabled />
                </div>
              </fieldset>

              <div class="actions">
                <button type="submit" class="button button-primary btn-save">Save changes</button>
                <span class="nova-inline-warning" id="nova-settings-status" aria-live="polite"></span>
              </div>
            </form>
          </section>
        `;
        $('#nova-backend-services').after(settingsCard);

        $('#nova-crawler-settings form').on('submit', async (event) => {
          event.preventDefault();
          await this.submitSettings();
        });
      }
    },

    async refreshDashboard() {
      try {
        const [health, status, metrics, models, config] = await Promise.all([
          this.safeFetch('/health'),
          this.safeFetch('/admin/crawler/status'),
          this.safeFetch('/admin/crawler/metrics'),
          this.safeFetch('/v1/models'),
          this.safeFetch('/admin/crawler/config'),
        ]);

        this.state.health = health;
        this.state.status = status;
        this.state.metrics = metrics;
        this.state.models = Array.isArray(models?.data) ? models.data : [];
        this.state.config = config || this.state.config;
        this.state.lastUpdated = new Date();

        this.renderBackendServices();
        this.renderSettingsPanel();
        this.updateLegacyStats();
      } catch (error) {
        console.error('[NovaAI][Dashboard]', error);
        const message = 'Unable to refresh backend status. Please verify API connectivity.';
        $('#nova-settings-message').text(message);
      }
    },

    async safeFetch(endpoint, options = {}) {
      try {
        return await this.fetchAPI(endpoint, options);
      } catch (error) {
        console.warn('[NovaAI][Fetch]', endpoint, error);
        return null;
      }
    },

    renderBackendServices() {
      const $grid = $('#nova-backend-services .nova-service-grid');
      if (!$grid.length) {
        return;
      }

      const status = this.state.status || {};
      const metrics = this.state.metrics || {};
      const userStatus = status.user_crawler || {};
      const autoStatus = status.auto_crawler || {};
      const publisherStatus = status.auto_publisher || {};
      const manager = status.main_manager || {};
      const overview = metrics.overview || {};
      const userMetrics = metrics.user_crawler?.metrics || userStatus.stats || {};
      const autoMetrics = metrics.auto_crawler?.metrics || {};

      const recentError = (timestamp) => {
        if (!timestamp) return false;
        const diff = Date.now() - Date.parse(timestamp);
        return diff < 15 * 60 * 1000; // 15 minutes
      };

      const formatPercent = (value) => {
        if (value === null || value === undefined || Number.isNaN(value)) {
          return '—';
        }
        return `${(value * 100).toFixed(1)}%`;
      };

      const userErrorRate = (userMetrics.pages_failed || 0) + (userMetrics.pages_crawled || 0)
        ? (userMetrics.pages_failed || 0) / ((userMetrics.pages_failed || 0) + (userMetrics.pages_crawled || 0))
        : 0;
      const autoErrorRate = (autoMetrics.pages_failed || 0) + (autoMetrics.pages_crawled || 0)
        ? (autoMetrics.pages_failed || 0) / ((autoMetrics.pages_failed || 0) + (autoMetrics.pages_crawled || 0))
        : 0;

      const services = [
        {
          name: 'API Health',
          status: (this.state.health && this.state.health.status === 'ok') ? 'ok' : 'err',
          meta: [
            `Status: <strong>${this.state.health?.status || 'unknown'}</strong>`,
            `Models available: <strong>${this.state.models.length}</strong>`,
            this.state.lastUpdated ? `Checked ${this.state.lastUpdated.toLocaleTimeString()}` : null,
          ].filter(Boolean),
        },
        {
          name: 'User Crawler',
          status: userStatus.running ? (recentError(userMetrics.last_error_at) ? 'warn' : 'ok') : 'err',
          meta: [
            `Workers: <strong>${userStatus.workers?.configured || userStatus.workers?.count || 0}</strong> (active ${userStatus.workers?.active_workers || userStatus.workers?.active || 0})`,
            `Queue: <strong>${userStatus.queues?.total || 0}</strong>`,
            `Error rate: <strong>${formatPercent(userErrorRate)}</strong>`,
          ],
        },
        {
          name: 'Auto Crawler',
          status: autoStatus && Object.values(autoStatus).some(item => item.running) ? (recentError(autoMetrics.last_error_at) ? 'warn' : 'ok') : 'warn',
          meta: [
            `Categories: <strong>${Object.keys(autoStatus || {}).length}</strong>`,
            `Queue: <strong>${metrics.auto_crawler?.queue_depth?.total || metrics.queue_depth?.total || 0}</strong>`,
            `Error rate: <strong>${formatPercent(autoErrorRate)}</strong>`,
          ],
        },
        {
          name: 'Auto Publisher',
          status: publisherStatus.running ? 'ok' : 'warn',
          meta: [
            `Interval: <strong>${publisherStatus.interval_seconds || 'n/a'}s</strong>`,
            `Max posts/h: <strong>${publisherStatus.max_posts_per_hour || 'n/a'}</strong>`,
          ],
        },
        {
          name: 'Crawler Manager',
          status: manager.active_workers > 0 ? 'ok' : 'warn',
          meta: [
            `Jobs total: <strong>${manager.total_jobs || overview.total_jobs || 0}</strong>`,
            `Queue total: <strong>${manager.queue_depth?.total || 0}</strong>`,
            `RAM buffer: <strong>${manager.memory_usage_bytes ? (manager.memory_usage_bytes / (1024 * 1024)).toFixed(1) : 0} MB</strong>`,
          ],
        },
      ];

      const badgeClass = (status) => {
        if (status === 'ok') return 'nova-badge nova-badge--ok';
        if (status === 'warn') return 'nova-badge nova-badge--warn';
        return 'nova-badge nova-badge--err';
      };

      const markup = services.map((service) => {
        const badgeText = service.status === 'ok' ? 'Running' : (service.status === 'warn' ? 'Attention' : 'Stopped');
        const meta = (service.meta || []).map(item => `<span>${item}</span>`).join('');
        return `
          <article class="nova-service-card">
            <div class="nova-service-header">
              <span class="nova-service-name">${service.name}</span>
              <span class="${badgeClass(service.status)}">${badgeText}</span>
            </div>
            <div class="nova-service-meta">${meta}</div>
          </article>
        `;
      }).join('');

      $grid.html(markup);
    },

    renderSettingsPanel() {
      const config = this.state.config;
      const $form = $('#nova-crawler-settings form');
      const $statusText = $('#nova-settings-status');
      const $message = $('#nova-settings-message');
      if (!$form.length) {
        return;
      }

      if (!config) {
        $message.text('Configuration unavailable.');
        return;
      }

      $message.text('');
      $('#nova-setting-user-workers').val(config.user_crawler_workers);
      $('#nova-setting-user-concurrency').val(config.user_crawler_max_concurrent);
      $('#nova-setting-auto-enabled').prop('checked', !!config.auto_crawler_enabled);
      $('#nova-setting-auto-workers').val(config.auto_crawler_workers);
      $('#nova-setting-flush').val(config.crawler_flush_interval);
      $('#nova-setting-retention').val(config.crawler_retention_days);
      $statusText.text('');
    },

    async submitSettings() {
      const $form = $('#nova-crawler-settings form');
      const $statusText = $('#nova-settings-status');
      const $button = $form.find('.btn-save');
      const config = this.state.config || {};

      const desired = {
        user_crawler_workers: parseInt($('#nova-setting-user-workers').val(), 10),
        user_crawler_max_concurrent: parseInt($('#nova-setting-user-concurrency').val(), 10),
        auto_crawler_enabled: $('#nova-setting-auto-enabled').is(':checked'),
      };

      const payload = {};
      Object.entries(desired).forEach(([key, value]) => {
        if (Number.isFinite(value) && config[key] !== value) {
          payload[key] = value;
        }
        if (typeof value === 'boolean' && config[key] !== value) {
          payload[key] = value;
        }
      });

      if (!Object.keys(payload).length) {
        $statusText.text('No changes to apply.');
        return;
      }

      try {
        $button.prop('disabled', true).text('Saving...');
        $statusText.text('Applying changes...');
        const response = await this.fetchAPI('/admin/crawler/config', {
          method: 'POST',
          body: JSON.stringify(payload),
        });

        if (response && response.config) {
          this.state.config = response.config;
          this.renderSettingsPanel();
          $statusText.text('Changes applied successfully.');
          if (window.showNotification) {
            window.showNotification('Crawler configuration updated', 'success');
          }
        } else {
          throw new Error('Unexpected response');
        }
      } catch (error) {
        console.error('[NovaAI][Settings]', error);
        $statusText.text('Failed to update settings.');
        if (window.showNotification) {
          window.showNotification('Failed to update crawler settings', 'error');
        }
      } finally {
        $button.prop('disabled', false).text('Save changes');
      }
    },

    updateLegacyStats() {
      const status = this.state.status || {};
      const health = this.state.health || {};

      const publisherEl = $('#nova-publisher-status');
      if (publisherEl.length) {
        publisherEl.text(status.auto_publisher?.running ? '✅ Aktiv' : '❌ Offline');
      }

      const crawlerEl = $('#nova-crawler-status');
      if (crawlerEl.length) {
        const queue = status.user_crawler?.queues?.total || 0;
        crawlerEl.text(status.user_crawler?.running ? `${queue} queued` : '❌ Offline');
      }

      const pendingEl = $('#nova-pending-results');
      if (pendingEl.length) {
        const total = this.state.metrics?.overview?.total_jobs || 0;
        pendingEl.text(total);
      }

      const healthEl = $('#nova-health-status');
      if (healthEl.length) {
        healthEl.text(health.status === 'ok' ? '✅' : '❌');
      }
    },

    /* ---------------------------------- */
    /* Legacy Crawler jobs table          */
    /* ---------------------------------- */

    async loadCrawlerJobs() {
      const $container = $('#nova-crawler-jobs-container');
      if (!$container.length) {
        return;
      }
      try {
        const jobs = await this.fetchAPI('/v1/crawler/jobs').catch(() => []);
        if (!jobs || !jobs.length) {
          $container.html('<p>No crawl jobs found.</p>');
          return;
        }

        const rows = jobs.map(job => `
          <tr>
            <td><code>${job.id}</code></td>
            <td>${(job.seeds || [])[0] || '—'}</td>
            <td><span class="status-badge ${job.status}">${job.status}</span></td>
            <td>${job.pages_crawled || 0} / ${job.max_pages}</td>
            <td>${job.results?.length || 0}</td>
            <td>${job.created_at ? new Date(job.created_at).toLocaleString() : '—'}</td>
          </tr>
        `).join('');

        const table = `
          <table class="wp-list-table widefat fixed striped">
            <thead>
              <tr>
                <th>ID</th>
                <th>Seed</th>
                <th>Status</th>
                <th>Pages</th>
                <th>Results</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        `;
        $container.html(table);
      } catch (error) {
        console.error('[NovaAI][CrawlerJobs]', error);
        $container.html('<p>Error loading crawl jobs.</p>');
      }
    },

    /* ---------------------------------- */
    /* Trigger publisher                  */
    /* ---------------------------------- */

    async triggerPublish() {
      const $button = $('#nova-trigger-publish');
      const $result = $('#nova-trigger-result');
      if (!$button.length) {
        return;
      }

      $button.prop('disabled', true).text('Running...');
      $result.empty();

      try {
        const response = await $.post(this.ajaxUrl, {
          action: 'nova_ai_trigger_publish',
          nonce: this.nonce,
        });

        if (response.success) {
          $result.html(`<div class="notice notice-success"><p>${response.data.message}</p></div>`);
          setTimeout(() => this.refreshDashboard(), 2000);
        } else {
          $result.html(`<div class="notice notice-error"><p>Error: ${response.data}</p></div>`);
        }
      } catch (error) {
        $result.html(`<div class="notice notice-error"><p>Error: ${error.message}</p></div>`);
      } finally {
        $button.prop('disabled', false).text('Publish now');
      }
    },

    /* ---------------------------------- */
    /* Shared fetch helper                */
    /* ---------------------------------- */

    async fetchAPI(endpoint, options = {}) {
      const url = this.apiBase.replace(/\/$/, '') + endpoint;
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), options.timeout || 20000);

      const defaults = {
        method: options.method || 'GET',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
          'X-AILinux-Client': 'nova-ai-admin/1.0',
          ...(options.headers || {}),
        },
        signal: controller.signal,
        body: options.body,
      };

      try {
        const response = await fetch(url, defaults);
        clearTimeout(timeout);
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          const message = payload.error?.message || `HTTP ${response.status}`;
          throw new Error(message);
        }
        return response.json();
      } finally {
        clearTimeout(timeout);
      }
    },
  };

  $(document).ready(() => NovaAIAdmin.init());
})(jQuery);
