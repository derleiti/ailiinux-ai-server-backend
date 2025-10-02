<?php
namespace NovaAI;

if (!defined('ABSPATH')) {
    exit;
}

/**
 * Admin Dashboard für Auto-Publisher Monitoring und Steuerung
 */
class AdminDashboard
{
    private const MENU_SLUG = 'nova-ai-dashboard';
    private const CAPABILITY = 'manage_options';

    public static function init(): void
    {
        add_action('admin_menu', [self::class, 'register_menu']);
        add_action('admin_enqueue_scripts', [self::class, 'enqueue_assets']);
        add_action('wp_ajax_nova_ai_get_stats', [self::class, 'ajax_get_stats']);
        add_action('wp_ajax_nova_ai_trigger_publish', [self::class, 'ajax_trigger_publish']);
    }

    public static function register_menu(): void
    {
        add_menu_page(
            __('Nova AI Dashboard', 'nova-ai-frontend'),
            __('Nova AI', 'nova-ai-frontend'),
            self::CAPABILITY,
            self::MENU_SLUG,
            [self::class, 'render_dashboard'],
            'dashicons-robot',
            30
        );

        add_submenu_page(
            self::MENU_SLUG,
            __('Auto-Publisher', 'nova-ai-frontend'),
            __('Auto-Publisher', 'nova-ai-frontend'),
            self::CAPABILITY,
            'nova-ai-auto-publisher',
            [self::class, 'render_auto_publisher']
        );

        add_submenu_page(
            self::MENU_SLUG,
            __('Crawler Status', 'nova-ai-frontend'),
            __('Crawler', 'nova-ai-frontend'),
            self::CAPABILITY,
            'nova-ai-crawler-status',
            [self::class, 'render_crawler_status']
        );
    }

    public static function enqueue_assets($hook): void
    {
        if (strpos($hook, 'nova-ai') === false) {
            return;
        }

        wp_enqueue_style(
            'nova-ai-admin',
            plugins_url('assets/admin.css', dirname(__FILE__)),
            [],
            '1.0.0'
        );

        wp_enqueue_script(
            'nova-ai-admin',
            plugins_url('assets/admin.js', dirname(__FILE__)),
            ['jquery'],
            '1.0.0',
            true
        );

        wp_localize_script('nova-ai-admin', 'novaAIAdmin', [
            'apiBase' => get_option('nova_ai_api_base', 'https://api.ailinux.me:9000'),
            'nonce' => wp_create_nonce('nova_ai_admin'),
            'ajaxUrl' => admin_url('admin-ajax.php'),
        ]);
    }

    public static function render_dashboard(): void
    {
        ?>
        <div class="wrap nova-ai-dashboard">
            <h1><?php _e('Nova AI Dashboard', 'nova-ai-frontend'); ?></h1>

            <div id="nova-dashboard-alert" class="nova-dashboard-alert" role="alert" aria-live="polite" hidden></div>

            <div class="nova-ai-stats-grid">
                <div class="nova-ai-stat-card">
                    <h2><?php _e('Auto-Publisher', 'nova-ai-frontend'); ?></h2>
                    <div class="stat-value" id="nova-publisher-status">
                        <span class="spinner is-active"></span>
                    </div>
                    <p class="stat-label"><?php _e('Status', 'nova-ai-frontend'); ?></p>
                </div>

                <div class="nova-ai-stat-card">
                    <h2><?php _e('Crawler', 'nova-ai-frontend'); ?></h2>
                    <div class="stat-value" id="nova-crawler-status">
                        <span class="spinner is-active"></span>
                    </div>
                    <p class="stat-label"><?php _e('User & Auto', 'nova-ai-frontend'); ?></p>
                </div>

                <div class="nova-ai-stat-card">
                    <h2><?php _e('Posts Heute', 'nova-ai-frontend'); ?></h2>
                    <div class="stat-value" id="nova-posts-today">
                        <span class="spinner is-active"></span>
                    </div>
                    <p class="stat-label"><?php _e('Automatisch erstellt', 'nova-ai-frontend'); ?></p>
                </div>

                <div class="nova-ai-stat-card">
                    <h2><?php _e('Wartend', 'nova-ai-frontend'); ?></h2>
                    <div class="stat-value" id="nova-pending-results">
                        <span class="spinner is-active"></span>
                    </div>
                    <p class="stat-label"><?php _e('Queue-Tiefe', 'nova-ai-frontend'); ?></p>
                </div>
            </div>

            <div class="nova-ops-grid">
                <section id="nova-backend-services" class="nova-card">
                    <div class="nova-card-header">
                        <h2><?php _e('Backend Services', 'nova-ai-frontend'); ?></h2>
                        <span class="brumo-icon" title="<?php esc_attr_e('Brumo approves', 'nova-ai-frontend'); ?>">🐾</span>
                    </div>
                    <div class="nova-service-grid">
                        <article class="nova-service-card" data-service="api">
                            <div class="nova-service-header">
                                <span class="nova-service-name"><?php _e('API Health', 'nova-ai-frontend'); ?></span>
                                <span class="nova-badge nova-badge--warn" id="nova-service-badge-api">—</span>
                            </div>
                            <div class="nova-service-meta" id="nova-service-meta-api"></div>
                        </article>
                        <article class="nova-service-card" data-service="user">
                            <div class="nova-service-header">
                                <span class="nova-service-name"><?php _e('User Crawler', 'nova-ai-frontend'); ?></span>
                                <span class="nova-badge nova-badge--warn" id="nova-service-badge-user">—</span>
                            </div>
                            <div class="nova-service-meta" id="nova-service-meta-user"></div>
                        </article>
                        <article class="nova-service-card" data-service="auto">
                            <div class="nova-service-header">
                                <span class="nova-service-name"><?php _e('Auto Crawler', 'nova-ai-frontend'); ?></span>
                                <span class="nova-badge nova-badge--warn" id="nova-service-badge-auto">—</span>
                            </div>
                            <div class="nova-service-meta" id="nova-service-meta-auto"></div>
                        </article>
                        <article class="nova-service-card" data-service="publisher">
                            <div class="nova-service-header">
                                <span class="nova-service-name"><?php _e('Auto-Publisher', 'nova-ai-frontend'); ?></span>
                                <span class="nova-badge nova-badge--warn" id="nova-service-badge-publisher">—</span>
                            </div>
                            <div class="nova-service-meta" id="nova-service-meta-publisher"></div>
                        </article>
                        <article class="nova-service-card" data-service="manager">
                            <div class="nova-service-header">
                                <span class="nova-service-name"><?php _e('Crawler Manager', 'nova-ai-frontend'); ?></span>
                                <span class="nova-badge nova-badge--warn" id="nova-service-badge-manager">—</span>
                            </div>
                            <div class="nova-service-meta" id="nova-service-meta-manager"></div>
                        </article>
                    </div>
                </section>

                <section id="nova-service-controls" class="nova-card">
                    <div class="nova-card-header">
                        <h2><?php _e('Crawler Controls', 'nova-ai-frontend'); ?></h2>
                        <span class="nova-inline-warning" id="nova-control-status"></span>
                    </div>
                    <div class="nova-control-grid">
                        <div class="nova-control-group" data-instance="user">
                            <h3><?php _e('User Crawler', 'nova-ai-frontend'); ?></h3>
                            <div class="nova-control-buttons">
                                <button type="button" class="button button-secondary nova-control-btn" data-instance="user" data-action="start"><?php _e('Start', 'nova-ai-frontend'); ?></button>
                                <button type="button" class="button button-secondary nova-control-btn" data-instance="user" data-action="stop"><?php _e('Stop', 'nova-ai-frontend'); ?></button>
                                <button type="button" class="button button-secondary nova-control-btn" data-instance="user" data-action="restart"><?php _e('Restart', 'nova-ai-frontend'); ?></button>
                            </div>
                        </div>
                        <div class="nova-control-group" data-instance="auto">
                            <h3><?php _e('Auto Crawler', 'nova-ai-frontend'); ?></h3>
                            <div class="nova-control-buttons">
                                <button type="button" class="button button-secondary nova-control-btn" data-instance="auto" data-action="start"><?php _e('Start', 'nova-ai-frontend'); ?></button>
                                <button type="button" class="button button-secondary nova-control-btn" data-instance="auto" data-action="stop"><?php _e('Stop', 'nova-ai-frontend'); ?></button>
                                <button type="button" class="button button-secondary nova-control-btn" data-instance="auto" data-action="restart"><?php _e('Restart', 'nova-ai-frontend'); ?></button>
                            </div>
                        </div>
                        <div class="nova-control-group" data-instance="publisher">
                            <h3><?php _e('Auto-Publisher', 'nova-ai-frontend'); ?></h3>
                            <div class="nova-control-buttons">
                                <button type="button" class="button button-secondary nova-control-btn" data-instance="publisher" data-action="start"><?php _e('Start', 'nova-ai-frontend'); ?></button>
                                <button type="button" class="button button-secondary nova-control-btn" data-instance="publisher" data-action="stop"><?php _e('Stop', 'nova-ai-frontend'); ?></button>
                                <button type="button" class="button button-secondary nova-control-btn" data-instance="publisher" data-action="restart"><?php _e('Restart', 'nova-ai-frontend'); ?></button>
                            </div>
                        </div>
                    </div>
                </section>

                <section id="nova-models-panel" class="nova-card">
                    <div class="nova-card-header">
                        <h2><?php _e('AI Models & MCP', 'nova-ai-frontend'); ?></h2>
                        <span class="nova-badge nova-badge--warn" id="nova-mcp-status">—</span>
                    </div>
                    <ul class="nova-model-list" id="nova-models-list">
                        <li><?php _e('Modelle werden geladen …', 'nova-ai-frontend'); ?></li>
                    </ul>
                </section>

                <section id="nova-crawler-settings" class="nova-card">
                    <div class="nova-card-header">
                        <h2><?php _e('Crawler Settings', 'nova-ai-frontend'); ?></h2>
                        <span class="nova-inline-warning" id="nova-settings-message"></span>
                    </div>
                    <form class="nova-settings" novalidate>
                        <fieldset>
                            <legend><?php _e('User Crawler', 'nova-ai-frontend'); ?></legend>
                            <div class="setting-row">
                                <label for="nova-setting-user-workers"><?php _e('Workers', 'nova-ai-frontend'); ?></label>
                                <input type="number" id="nova-setting-user-workers" min="1" step="1" data-field="user_crawler_workers" />
                                <p class="setting-help"><?php _e('Dedizierte Worker für User-Jobs.', 'nova-ai-frontend'); ?></p>
                            </div>
                            <div class="setting-row">
                                <label for="nova-setting-user-concurrency"><?php _e('Max Concurrent Pages', 'nova-ai-frontend'); ?></label>
                                <input type="number" id="nova-setting-user-concurrency" min="1" step="1" data-field="user_crawler_max_concurrent" />
                                <p class="setting-help"><?php _e('Parallel abrufbare Seiten des User-Crawlers.', 'nova-ai-frontend'); ?></p>
                            </div>
                        </fieldset>

                        <fieldset>
                            <legend><?php _e('Auto Crawler', 'nova-ai-frontend'); ?></legend>
                            <div class="setting-row">
                                <label class="toggle-label" for="nova-setting-auto-enabled">
                                    <input type="checkbox" id="nova-setting-auto-enabled" data-field="auto_crawler_enabled" />
                                    <span><?php _e('Auto Crawler aktiv', 'nova-ai-frontend'); ?></span>
                                </label>
                                <p class="setting-help"><?php _e('24/7 Hintergrundcrawler aktivieren oder stoppen.', 'nova-ai-frontend'); ?></p>
                            </div>
                            <div class="setting-row">
                                <label for="nova-setting-auto-workers"><?php _e('Worker (konfiguriert)', 'nova-ai-frontend'); ?></label>
                                <input type="number" id="nova-setting-auto-workers" data-field="auto_crawler_workers" disabled />
                            </div>
                        </fieldset>

                        <fieldset>
                            <legend><?php _e('Retention & Flush', 'nova-ai-frontend'); ?></legend>
                            <div class="setting-row">
                                <label for="nova-setting-flush"><?php _e('Flush Interval (Sekunden)', 'nova-ai-frontend'); ?></label>
                                <input type="number" id="nova-setting-flush" data-field="crawler_flush_interval" disabled />
                            </div>
                            <div class="setting-row">
                                <label for="nova-setting-retention"><?php _e('Retention (Tage)', 'nova-ai-frontend'); ?></label>
                                <input type="number" id="nova-setting-retention" data-field="crawler_retention_days" disabled />
                            </div>
                        </fieldset>

                        <div class="actions">
                            <button type="submit" class="button button-primary btn-save"><?php _e('Save changes', 'nova-ai-frontend'); ?></button>
                            <span class="nova-inline-warning" id="nova-settings-status" aria-live="polite"></span>
                        </div>
                    </form>
                </section>
            </div>

            <!-- Recent Auto-Posts -->
            <div class="nova-ai-recent-posts">
                <h2><?php _e('Kürzlich automatisch erstellt', 'nova-ai-frontend'); ?></h2>
                <table class="wp-list-table widefat fixed striped">
                    <thead>
                        <tr>
                            <th><?php _e('Titel', 'nova-ai-frontend'); ?></th>
                            <th><?php _e('Score', 'nova-ai-frontend'); ?></th>
                            <th><?php _e('Quelle', 'nova-ai-frontend'); ?></th>
                            <th><?php _e('Erstellt', 'nova-ai-frontend'); ?></th>
                            <th><?php _e('Aktionen', 'nova-ai-frontend'); ?></th>
                        </tr>
                    </thead>
                    <tbody id="nova-recent-posts-tbody">
                        <tr>
                            <td colspan="5" style="text-align:center;">
                                <span class="spinner is-active"></span>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
        <?php
    }

    public static function render_auto_publisher(): void
    {
        $enabled = get_option('nova_ai_crawler_enabled', 0);
        $category = get_option('nova_ai_crawler_category', 0);
        $forum = get_option('nova_ai_crawler_forum', 0);
        $author = get_option('nova_ai_crawler_author', get_current_user_id());

        ?>
        <div class="wrap nova-ai-auto-publisher">
            <h1><?php _e('Auto-Publisher Einstellungen', 'nova-ai-frontend'); ?></h1>

            <form method="post" action="options.php">
                <?php
                settings_fields('nova_ai_settings');
                do_settings_sections('nova-ai-settings');
                ?>

                <table class="form-table">
                    <tr>
                        <th scope="row">
                            <label for="nova_ai_crawler_enabled">
                                <?php _e('Auto-Publishing aktiviert', 'nova-ai-frontend'); ?>
                            </label>
                        </th>
                        <td>
                            <input type="checkbox"
                                   id="nova_ai_crawler_enabled"
                                   name="nova_ai_crawler_enabled"
                                   value="1"
                                   <?php checked($enabled, 1); ?>>
                            <p class="description">
                                <?php _e('Crawler-Ergebnisse automatisch als Posts und Forum-Topics veröffentlichen', 'nova-ai-frontend'); ?>
                            </p>
                        </td>
                    </tr>

                    <tr>
                        <th scope="row">
                            <label for="nova_ai_crawler_category">
                                <?php _e('Standard-Kategorie', 'nova-ai-frontend'); ?>
                            </label>
                        </th>
                        <td>
                            <?php
                            wp_dropdown_categories([
                                'name' => 'nova_ai_crawler_category',
                                'id' => 'nova_ai_crawler_category',
                                'selected' => $category,
                                'show_option_none' => __('Keine Kategorie', 'nova-ai-frontend'),
                                'option_none_value' => 0,
                                'hide_empty' => false,
                            ]);
                            ?>
                            <p class="description">
                                <?php _e('Kategorie für automatisch erstellte Posts', 'nova-ai-frontend'); ?>
                            </p>
                        </td>
                    </tr>

                    <tr>
                        <th scope="row">
                            <label for="nova_ai_crawler_forum">
                                <?php _e('Standard-Forum', 'nova-ai-frontend'); ?>
                            </label>
                        </th>
                        <td>
                            <?php if (function_exists('bbp_get_forum_id')): ?>
                                <select name="nova_ai_crawler_forum" id="nova_ai_crawler_forum">
                                    <option value="0"><?php _e('Kein Forum', 'nova-ai-frontend'); ?></option>
                                    <?php
                                    $forums = get_posts([
                                        'post_type' => 'forum',
                                        'posts_per_page' => -1,
                                    ]);
                                    foreach ($forums as $f) {
                                        printf(
                                            '<option value="%d" %s>%s</option>',
                                            $f->ID,
                                            selected($forum, $f->ID, false),
                                            esc_html($f->post_title)
                                        );
                                    }
                                    ?>
                                </select>
                                <p class="description">
                                    <?php _e('Forum für automatisch erstellte Topics', 'nova-ai-frontend'); ?>
                                </p>
                            <?php else: ?>
                                <p class="description">
                                    <?php _e('bbPress nicht installiert', 'nova-ai-frontend'); ?>
                                </p>
                            <?php endif; ?>
                        </td>
                    </tr>

                    <tr>
                        <th scope="row">
                            <label for="nova_ai_crawler_author">
                                <?php _e('Autor für Posts', 'nova-ai-frontend'); ?>
                            </label>
                        </th>
                        <td>
                            <?php
                            wp_dropdown_users([
                                'name' => 'nova_ai_crawler_author',
                                'id' => 'nova_ai_crawler_author',
                                'selected' => $author,
                                'show_option_all' => false,
                                'show_option_none' => false,
                            ]);
                            ?>
                            <p class="description">
                                <?php _e('Nutzer als Autor für automatisch erstellte Posts', 'nova-ai-frontend'); ?>
                            </p>
                        </td>
                    </tr>
                </table>

                <?php submit_button(); ?>
            </form>

            <!-- Manual Trigger -->
            <hr>
            <h2><?php _e('Manuelle Ausführung', 'nova-ai-frontend'); ?></h2>
            <p>
                <?php _e('Sofort neue Crawler-Ergebnisse prüfen und veröffentlichen (normalerweise automatisch stündlich)', 'nova-ai-frontend'); ?>
            </p>
            <button type="button" class="button button-primary" id="nova-trigger-publish">
                <?php _e('Jetzt veröffentlichen', 'nova-ai-frontend'); ?>
            </button>
            <div id="nova-trigger-result" style="margin-top:10px;"></div>
        </div>
        <?php
    }

    public static function render_crawler_status(): void
    {
        ?>
        <div class="wrap nova-ai-crawler-status">
            <h1><?php _e('Crawler Status', 'nova-ai-frontend'); ?></h1>

            <div id="nova-crawler-jobs-container">
                <span class="spinner is-active"></span>
            </div>
        </div>
        <?php
    }

    public static function ajax_get_stats(): void
    {
        check_ajax_referer('nova_ai_admin', 'nonce');

        if (!current_user_can(self::CAPABILITY)) {
            wp_send_json_error('Unauthorized', 403);
        }

        $api_base = get_option('nova_ai_api_base', 'https://api.ailinux.me:9000');

        // Hole Stats von Backend
        $response = wp_remote_get($api_base . '/v1/crawler/jobs');

        if (is_wp_error($response)) {
            wp_send_json_error('Backend unreachable');
        }

        $jobs = json_decode(wp_remote_retrieve_body($response), true);

        // Hole Posts von heute (auto-created)
        $today_posts = get_posts([
            'post_type' => 'post',
            'date_query' => [
                [
                    'after' => 'today',
                ],
            ],
            'meta_query' => [
                [
                    'key' => '_nova_ai_auto_created',
                    'value' => '1',
                ],
            ],
            'posts_per_page' => -1,
        ]);

        wp_send_json_success([
            'jobs' => $jobs,
            'posts_today' => count($today_posts),
            'recent_posts' => array_map(function ($post) {
                return [
                    'id' => $post->ID,
                    'title' => $post->post_title,
                    'date' => $post->post_date,
                    'url' => get_permalink($post),
                ];
            }, array_slice($today_posts, 0, 10)),
        ]);
    }

    public static function ajax_trigger_publish(): void
    {
        check_ajax_referer('nova_ai_admin', 'nonce');

        if (!current_user_can(self::CAPABILITY)) {
            wp_send_json_error('Unauthorized', 403);
        }

        // Trigger Backend Auto-Publisher Manual Run
        $api_base = get_option('nova_ai_api_base', 'https://api.ailinux.me:9000');

        $response = wp_remote_post($api_base . '/v1/auto-publisher/trigger', [
            'timeout' => 60,
            'headers' => [
                'Content-Type' => 'application/json',
            ],
        ]);

        if (is_wp_error($response)) {
            wp_send_json_error('Backend nicht erreichbar: ' . $response->get_error_message());
            return;
        }

        $body = json_decode(wp_remote_retrieve_body($response), true);

        if ($body['status'] === 'success') {
            wp_send_json_success([
                'message' => $body['message'],
            ]);
        } else {
            wp_send_json_error($body['message'] ?? 'Unbekannter Fehler');
        }
    }
}
