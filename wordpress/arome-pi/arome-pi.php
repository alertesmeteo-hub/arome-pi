<?php
/**
 * Plugin Name: AROME-PI Météo-France France — Tableaux et cartes
 * Plugin URI: https://github.com/alertesmeteo-hub/arome-pi
 * Description: Module unique de cartes interactives et de prévisions AROME-PI de Météo-France pour la France métropolitaine et la Corse.
 * Version: 1.0.4
 * Author: Alertes Météo Hub
 * Requires at least: 5.8
 * Requires PHP: 7.4
 * License: GPL-2.0-or-later
 */

if (!defined('ABSPATH')) {
    exit;
}

define('AMPI_VERSION', '1.0.4');
define('AMPI_RELEASE_DATE', '11/09/2026');
define('AMPI_OPTION_BASE_URL', 'ampi_national_data_base_url');
define(
    'AMPI_DEFAULT_BASE_URL',
    'https://raw.githubusercontent.com/alertesmeteo-hub/arome-pi/data'
);

// Auto-guérison du pipeline AROME-PI : si index.json est resté bloqué trop
// longtemps (cron GitHub Actions peu fiable), chaque chargement de la page
// relance côté serveur un nouveau run via workflow_dispatch. Le jeton
// GitHub reste EXCLUSIVEMENT côté serveur — à définir dans wp-config.php :
//   define('AMPI_GITHUB_TOKEN', 'github_pat_xxx...');
// Jeton « fine-grained », limité au dépôt alertesmeteo-hub/arome-pi,
// permission « Actions » en Read and write.
define('AMPI_GITHUB_REPO', 'alertesmeteo-hub/arome-pi');
define('AMPI_GITHUB_DATA_BRANCH', 'data');
define('AMPI_GITHUB_WORKFLOW_BRANCH', 'main');
define('AMPI_GITHUB_WORKFLOW_FILE', 'update-arome-pi.yml');
// AROME-PI tourne toutes les heures : une production vieille de plus de
// deux heures est considérée comme obsolète.
define('AMPI_STALE_THRESHOLD_MIN', 2 * 60);

add_action('wp_enqueue_scripts', 'ampi_register_assets');
add_action('admin_init', 'ampi_register_settings');
add_action('admin_menu', 'ampi_add_settings_page');
add_shortcode('aromepi_meteo', 'ampi_render_shortcode');
add_filter('plugin_action_links_' . plugin_basename(__FILE__), 'ampi_plugin_action_links');
add_action('wp_ajax_ampi_autoheal', 'ampi_handle_autoheal');
add_action('wp_ajax_nopriv_ampi_autoheal', 'ampi_handle_autoheal');

function ampi_handle_autoheal() {
    if (!defined('AMPI_GITHUB_TOKEN') || !AMPI_GITHUB_TOKEN) {
        wp_send_json_success(array('configured' => false));
    }

    if (get_transient('ampi_autoheal_lock')) {
        wp_send_json_success(array('skipped' => true));
    }
    set_transient('ampi_autoheal_lock', 1, 5 * MINUTE_IN_SECONDS);

    $generated_at = ampi_fetch_generated_at();
    if (null === $generated_at) {
        wp_send_json_success(array('configured' => true, 'checked' => false));
    }

    $age_minutes = (time() - $generated_at) / 60;
    if ($age_minutes <= AMPI_STALE_THRESHOLD_MIN) {
        wp_send_json_success(array('configured' => true, 'stale' => false, 'age_minutes' => round($age_minutes)));
    }

    if (get_transient('ampi_autoheal_cooldown')) {
        wp_send_json_success(array('configured' => true, 'stale' => true, 'triggered' => false, 'cooldown' => true));
    }
    set_transient('ampi_autoheal_cooldown', 1, 30 * MINUTE_IN_SECONDS);

    $triggered = ampi_trigger_workflow();
    wp_send_json_success(array('configured' => true, 'stale' => true, 'triggered' => $triggered));
}

function ampi_fetch_generated_at() {
    $url = 'https://api.github.com/repos/' . AMPI_GITHUB_REPO . '/contents/index.json'
        . '?ref=' . rawurlencode(AMPI_GITHUB_DATA_BRANCH);
    $response = wp_remote_get($url, array(
        'headers' => array(
            'Accept'     => 'application/vnd.github.raw',
            'User-Agent' => 'arome-pi-autoheal',
        ),
        'timeout' => 8,
    ));
    if (is_wp_error($response) || 200 !== wp_remote_retrieve_response_code($response)) {
        return null;
    }
    $data = json_decode(wp_remote_retrieve_body($response), true);
    if (empty($data['generated_at'])) {
        return null;
    }
    $timestamp = strtotime($data['generated_at']);
    return $timestamp ? $timestamp : null;
}

function ampi_trigger_workflow() {
    $url = 'https://api.github.com/repos/' . AMPI_GITHUB_REPO . '/actions/workflows/'
        . rawurlencode(AMPI_GITHUB_WORKFLOW_FILE) . '/dispatches';
    $response = wp_remote_post($url, array(
        'headers' => array(
            'Accept'        => 'application/vnd.github+json',
            'Authorization' => 'Bearer ' . AMPI_GITHUB_TOKEN,
            'Content-Type'  => 'application/json',
            'User-Agent'    => 'arome-pi-autoheal',
        ),
        'body'    => wp_json_encode(array('ref' => AMPI_GITHUB_WORKFLOW_BRANCH)),
        'timeout' => 8,
    ));
    if (is_wp_error($response)) {
        return false;
    }
    $code = wp_remote_retrieve_response_code($response);
    return $code >= 200 && $code < 300;
}

function ampi_plugin_action_links($links) {
    $settings_link = sprintf(
        '<a href="%s">%s</a>',
        esc_url(admin_url('options-general.php?page=arome-pi')),
        esc_html__('Réglages', 'arome-pi')
    );
    array_unshift($links, $settings_link);

    $help_link = sprintf(
        '<a href="%s">%s</a>',
        esc_url(admin_url('options-general.php?page=arome-pi')),
        esc_html__('Shortcodes / Aide', 'arome-pi')
    );
    array_unshift($links, $help_link);

    return $links;
}

function ampi_register_assets() {
    wp_register_style(
        'ampi-table',
        plugin_dir_url(__FILE__) . 'assets/arome-meteo.css',
        array(),
        AMPI_VERSION
    );
    wp_register_script(
        'ampi-table',
        plugin_dir_url(__FILE__) . 'assets/arome-meteo.js',
        array(),
        AMPI_VERSION,
        true
    );
    wp_register_style(
        'ampi-map',
        plugin_dir_url(__FILE__) . 'assets/arome-map.css',
        array('ampi-table'),
        AMPI_VERSION
    );
    wp_register_script(
        'ampi-map',
        plugin_dir_url(__FILE__) . 'assets/arome-map.js',
        array(),
        AMPI_VERSION,
        true
    );
    wp_localize_script('ampi-table', 'AMPI_AUTOHEAL', array(
        'url' => admin_url('admin-ajax.php?action=ampi_autoheal'),
    ));
}

function ampi_register_settings() {
    register_setting(
        'ampi_settings',
        AMPI_OPTION_BASE_URL,
        array(
            'type' => 'string',
            'sanitize_callback' => 'esc_url_raw',
            'default' => AMPI_DEFAULT_BASE_URL,
        )
    );

    add_settings_section(
        'ampi_main_section',
        'Source des données nationales',
        '__return_false',
        'arome-pi'
    );

    add_settings_field(
        'ampi_data_base_url_field',
        'Adresse du dossier de données',
        'ampi_render_url_field',
        'arome-pi',
        'ampi_main_section'
    );
}

function ampi_render_url_field() {
    $value = get_option(AMPI_OPTION_BASE_URL, AMPI_DEFAULT_BASE_URL);
    printf(
        '<input type="url" class="regular-text code" name="%1$s" value="%2$s" autocomplete="off">',
        esc_attr(AMPI_OPTION_BASE_URL),
        esc_attr($value)
    );
    echo '<p class="description">Conservez l’adresse proposée : elle pointe vers la branche nationale « data » du dépôt.</p>';
}

function ampi_add_settings_page() {
    add_options_page(
        'Tableau AROME-PI Météo-France France',
        'AROME-PI Météo-France',
        'manage_options',
        'arome-pi',
        'ampi_render_settings_page'
    );
}

function ampi_render_settings_page() {
    if (!current_user_can('manage_options')) {
        return;
    }
    ?>
    <div class="wrap">
        <h1>AROME-PI Météo-France France</h1>
        <form action="options.php" method="post">
            <?php
            settings_fields('ampi_settings');
            do_settings_sections('arome-pi');
            submit_button();
            ?>
        </form>
        <p><strong>Version du module : <?php echo esc_html(AMPI_VERSION); ?> (<?php echo esc_html(AMPI_RELEASE_DATE); ?>)</strong></p>
        <h2>Shortcode unique</h2>
        <p><code>[aromepi_meteo]</code> : cartes interactives, prévisions générales, orages, neige et graphiques.</p>
        <p><code>[aromepi_meteo code="75056" departement="75" ville="Paris" heures="6"]</code></p>
        <p><code>[aromepi_meteo code="66136" departement="66" ville="Perpignan" selecteur="non"]</code> : une seule ville, sans recherche.</p>
        <p>Le visiteur peut ensuite rechercher n’importe quelle commune ou saisir un code postal.</p>
        <h2>Auto-guérison du pipeline</h2>
        <p>
            Statut : <strong><?php echo (defined('AMPI_GITHUB_TOKEN') && AMPI_GITHUB_TOKEN) ? '✅ Configurée' : '⚠️ Non configurée'; ?></strong>
        </p>
        <p>
            Si <code>index.json</code> reste bloqué plus de <?php echo esc_html((int) round(AMPI_STALE_THRESHOLD_MIN / 60)); ?> heures,
            chaque chargement de cette page relance automatiquement le pipeline sur GitHub. Pour l'activer, ajouter dans
            <code>wp-config.php</code> :
        </p>
        <p><code>define('AMPI_GITHUB_TOKEN', 'github_pat_xxx...');</code></p>
        <p>
            Jeton « fine-grained » GitHub, limité au dépôt <code>alertesmeteo-hub/arome-pi</code>, permission
            « Actions : Read and write » uniquement. Il n'est jamais transmis au navigateur.
        </p>
    </div>
    <?php
}

function ampi_base_url() {
    $url = get_option(AMPI_OPTION_BASE_URL, AMPI_DEFAULT_BASE_URL);
    return untrailingslashit(apply_filters('ampi_national_data_base_url', $url));
}

function ampi_department_code($value) {
    $code = strtoupper(trim((string) $value));
    return preg_match('/^(?:\d{2}|2A|2B)$/', $code) ? $code : '66';
}

function ampi_commune_code($value) {
    $code = strtoupper(trim((string) $value));
    return preg_match('/^[0-9A-Z]{5}$/', $code) ? $code : '66136';
}

function ampi_unique_identifier() {
    if (function_exists('wp_unique_id')) {
        return wp_unique_id('ampi-city-');
    }
    return 'ampi-city-' . wp_rand(1000, 999999);
}

function ampi_map_variable($value) {
    $variable = strtolower(trim(sanitize_key((string) $value)));
    $allowed = array(
        'temperature',
        'temperature_ressentie',
        'thermometre_mouille',
        'point_rosee',
        'humidex',
        'pluie_1h',
        'pluie_cumul',
        'neige',
        'neige_au_sol',
        'equivalent_eau_neige',
        'graupel',
        'neige_graupel',
        'grele',
        'type_precipitation_severe',
        'vent',
        'rafales',
        'pression',
        'pression_surface',
        'nebulosite',
        'nuages_bas',
        'nuages_moyens',
        'nuages_eleves',
        'humidite',
        'mucape',
        'reflectivite',
        'altitude',
    );
    return in_array($variable, $allowed, true) ? $variable : 'temperature';
}

function ampi_render_map_shortcode($atts) {
    $atts = shortcode_atts(
        array(
            'variable' => 'temperature',
            'hauteur' => '700',
            'titre' => 'Cartes AROME-PI France',
            'animation' => 'oui',
            'vue' => 'france',
        ),
        $atts,
        'aromepi_meteo'
    );

    $variable = ampi_map_variable($atts['variable']);
    $height = max(440, min(1100, absint($atts['hauteur'])));
    $title = trim(sanitize_text_field($atts['titre']));
    if ($title === '') {
        $title = 'Cartes AROME-PI France';
    }
    $animation_value = strtolower(trim(sanitize_text_field($atts['animation'])));
    $animation = !in_array($animation_value, array('non', '0', 'false', 'off'), true);
    $map_view = strtolower(trim(sanitize_key($atts['vue'])));
    $map_view = in_array($map_view, array('france', 'europe'), true) ? $map_view : 'france';
    $map_id = function_exists('wp_unique_id')
        ? wp_unique_id('ampi-map-')
        : 'ampi-map-' . wp_rand(1000, 999999);

    wp_enqueue_style('ampi-map');
    wp_enqueue_script('ampi-map');

    ob_start();
    ?>
    <section
        id="<?php echo esc_attr($map_id); ?>"
        class="ampi-card ampim-card"
        data-ampim-app
        data-base-url="<?php echo esc_url(ampi_base_url()); ?>"
        data-variable="<?php echo esc_attr($variable); ?>"
        data-timezone="<?php echo esc_attr(wp_timezone_string()); ?>"
        data-animation="<?php echo $animation ? '1' : '0'; ?>"
        data-module-version="<?php echo esc_attr(AMPI_VERSION); ?>"
        data-map-view="<?php echo esc_attr($map_view); ?>"
        style="--ampim-height: <?php echo esc_attr($height); ?>px"
    >
        <header class="ampi-header ampim-header">
            <div>
                <p class="ampi-kicker">MODÈLE HAUTE RÉSOLUTION • ÉCHÉANCES HORAIRES</p>
                <h2><?php echo esc_html($title); ?></h2>
                <p class="ampi-meta" data-ampim-run>Chargement du dernier run AROME-PI…</p>
            </div>
            <div class="ampi-badge">AROME-PI<br><strong>1,3 km</strong></div>
        </header>

        <div class="ampim-toolbar">
            <div class="ampim-field ampim-layer-picker">
                <span>Paramètre</span>
                <button
                    type="button"
                    class="ampim-layer-trigger"
                    data-ampim-menu-toggle
                    aria-expanded="false"
                    aria-controls="<?php echo esc_attr($map_id . '-layers'); ?>"
                >
                    <span data-ampim-current-layer>Température à 2 m</span>
                    <span class="ampim-layer-chevron" aria-hidden="true">⌄</span>
                </button>
            </div>
            <div class="ampim-tools" aria-label="Outils de la carte">
                <button
                    type="button"
                    class="ampim-tool-toggle"
                    data-ampim-capture
                    title="Télécharger la carte affichée"
                >📷 Capture</button>
                <button
                    type="button"
                    class="ampim-tool-toggle"
                    data-ampim-tool="diagram"
                    aria-pressed="false"
                    title="Cliquer sur la carte pour afficher le diagramme d’un point"
                >📈 Diagramme</button>
                <button
                    type="button"
                    class="ampim-tool-toggle"
                    data-ampim-recenter-city
                    title="Recentrer la carte sur la commune choisie"
                >⌾ Recentrer ville</button>
                <button
                    type="button"
                    class="ampim-tool-toggle"
                    data-ampim-fullscreen
                    title="Afficher la carte en plein écran"
                >⛶ Plein écran</button>
            </div>
            <div class="ampim-time-controls" aria-label="Navigation dans les échéances">
                <button type="button" data-ampim-previous title="Échéance précédente" aria-label="Échéance précédente">◀</button>
                <button type="button" data-ampim-play title="Lancer l’animation" aria-label="Lancer l’animation">▶</button>
                <button type="button" data-ampim-next title="Échéance suivante" aria-label="Échéance suivante">▶</button>
            </div>
            <div class="ampim-validity">
                <span>Prévision valable</span>
                <strong data-ampim-validity>—</strong>
                <small data-ampim-lead>—</small>
            </div>
        </div>

        <p class="ampim-tool-hint" data-ampim-tool-hint hidden></p>

        <div
            id="<?php echo esc_attr($map_id . '-layers'); ?>"
            class="ampim-layer-menu"
            data-ampim-layer-menu
            hidden
        >
            <div class="ampim-layer-menu-head">
                <div>
                    <strong>Choisir une carte AROME-PI</strong>
                    <small>Uniquement les paramètres disponibles dans la production Météo-France</small>
                </div>
                <button type="button" data-ampim-menu-close aria-label="Réduire le menu">×</button>
            </div>
            <div class="ampim-layer-grid" data-ampim-layer-grid></div>
        </div>

        <div class="ampim-period-selector" data-ampim-period hidden>
            <div class="ampim-period-head">
                <div>
                    <strong data-ampim-period-title>Période personnalisée</strong>
                    <small>Déplacez les deux curseurs pour choisir précisément le début et la fin.</small>
                </div>
                <span data-ampim-period-summary>—</span>
            </div>
            <div class="ampim-dual-range" data-ampim-dual-range>
                <div class="ampim-dual-range-track" aria-hidden="true"></div>
                <input data-ampim-period-start type="range" min="0" max="1" value="0" step="1" aria-label="Début de la période">
                <input data-ampim-period-end type="range" min="0" max="1" value="1" step="1" aria-label="Fin de la période">
            </div>
            <div class="ampim-period-values">
                <span><small>Du</small><strong data-ampim-period-start-label>—</strong></span>
                <span><small>Au</small><strong data-ampim-period-end-label>—</strong></span>
            </div>
        </div>

        <p class="ampi-stale" data-ampim-stale role="status" hidden>
            Attention : la dernière production AROME-PI disponible a plus de 2 heures.
        </p>

        <div class="ampim-viewport" data-ampim-viewport role="img" aria-label="Carte météo AROME-PI interactive">
            <div class="ampim-scene" data-ampim-scene>
                <canvas class="ampim-weather-canvas" data-ampim-weather aria-hidden="true"></canvas>
                <canvas class="ampim-vector-canvas" data-ampim-vectors aria-hidden="true"></canvas>
            </div>
            <canvas class="ampim-label-canvas" data-ampim-labels aria-hidden="true"></canvas>
            <div class="ampim-probe" data-ampim-probe hidden>
                <strong data-ampim-probe-value>—</strong>
                <span data-ampim-probe-label>Valeur AROME-PI</span>
            </div>
            <div class="ampim-map-titlebar">
                <strong data-ampim-map-title>Carte AROME-PI</strong>
                <span data-ampim-map-run>Run AROME-PI —</span>
            </div>
            <div class="ampim-map-date" data-ampim-map-date>Échéance —</div>
            <div class="ampim-map-buttons" aria-label="Commandes de zoom">
                <span class="ampim-zoom-level" data-ampim-zoom-level>100 %</span>
                <button type="button" data-ampim-zoom-in title="Agrandir" aria-label="Agrandir">+</button>
                <button type="button" data-ampim-zoom-out title="Réduire" aria-label="Réduire">−</button>
                <button type="button" data-ampim-reset title="Voir toute la zone" aria-label="Voir toute la zone">⌂</button>
            </div>
            <div class="ampim-advanced-tools" data-ampim-advanced-tools hidden aria-label="Outils avancés">
                <button type="button" data-ampim-pin title="Épingler la valeur au clic" aria-label="Épingler la valeur au clic" aria-pressed="false">📌 Figer la valeur</button>
            </div>
            <div class="ampim-diagram-popup" data-ampim-diagram-popup hidden>
                <header>
                    <strong data-ampim-diagram-title>—</strong>
                    <button type="button" data-ampim-diagram-close aria-label="Fermer le diagramme">×</button>
                </header>
                <div class="ampim-diagram-body" data-ampim-diagram-body>
                    <p class="ampim-diagram-status" data-ampim-diagram-status>Chargement…</p>
                </div>
            </div>
            <div class="ampim-legend" data-ampim-legend aria-label="Légende de la carte"></div>
            <a class="ampim-map-brand" href="https://www.alertes-meteo.com/" target="_blank" rel="noopener noreferrer">
                www.alertes-meteo.com
            </a>
            <div class="ampim-loading" data-ampim-loading role="status">Chargement de la carte…</div>
            <div class="ampim-error" data-ampim-error role="alert" hidden></div>
        </div>

        <div class="ampim-timeline" data-ampim-timeline>
            <input data-ampim-slider type="range" min="0" max="0" value="0" step="1" aria-label="Échéance de prévision">
            <div class="ampim-timeline-labels"><span>Run</span><span>Échéance maximale</span></div>
        </div>

        <footer class="ampi-footer">
            <span data-ampim-generated>Mise à jour en cours de lecture…</span>
            <span>
                Données météo directes :
                <a href="https://www.data.gouv.fr/dataservices/api-modele-arome-prevision-immediate" target="_blank" rel="noopener noreferrer">API AROME Prévision Immédiate — Météo-France</a>
                • <a href="https://www.alertes-meteo.com/" target="_blank" rel="noopener noreferrer">www.alertes-meteo.com</a>
                • Module cartes v<?php echo esc_html(AMPI_VERSION); ?> (<?php echo esc_html(AMPI_RELEASE_DATE); ?>)
            </span>
        </footer>

        <noscript>
            <p class="ampi-message ampi-error">JavaScript doit être activé pour afficher les cartes.</p>
        </noscript>
    </section>
    <?php
    return ob_get_clean();
}

function ampi_render_shortcode($atts) {
    $atts = shortcode_atts(
        array(
            'ville' => 'Perpignan',
            'code' => '66136',
            'departement' => '66',
            'heures' => '6',
            'titre' => '',
            'selecteur' => 'oui',
        ),
        $atts,
        'aromepi_meteo'
    );

    $hours = max(1, min(6, absint($atts['heures'])));
    $city_name = sanitize_text_field($atts['ville']);
    if ($city_name === '') {
        $city_name = 'Perpignan';
    }
    $city_code = ampi_commune_code($atts['code']);
    $department = ampi_department_code($atts['departement']);
    $title_prefix = trim(sanitize_text_field($atts['titre']));
    if ($title_prefix === '') {
        $title_prefix = 'Prévisions AROME-PI';
    }
    $selector_value = strtolower(trim(sanitize_text_field($atts['selecteur'])));
    $show_selector = !in_array($selector_value, array('non', '0', 'false', 'off'), true);

    $input_id = ampi_unique_identifier();
    $results_id = $input_id . '-results';
    $status_id = $input_id . '-status';

    wp_enqueue_style('ampi-table');
    wp_enqueue_script('ampi-table');
    wp_enqueue_style('ampi-map');
    wp_enqueue_script('ampi-map');

    ob_start();
    ?>
    <section
        class="ampi-card ampi-national"
        data-ampi-app
        data-base-url="<?php echo esc_url(ampi_base_url()); ?>"
        data-default-code="<?php echo esc_attr($city_code); ?>"
        data-default-department="<?php echo esc_attr($department); ?>"
        data-default-name="<?php echo esc_attr($city_name); ?>"
        data-hours="<?php echo esc_attr($hours); ?>"
        data-timezone="<?php echo esc_attr(wp_timezone_string()); ?>"
        data-title-prefix="<?php echo esc_attr($title_prefix); ?>"
        data-selector="<?php echo $show_selector ? '1' : '0'; ?>"
    >
        <header class="ampi-header">
            <div>
                <p class="ampi-kicker">MODÈLE HAUTE RÉSOLUTION • FRANCE MÉTROPOLITAINE</p>
                <h2 data-ampi-title><?php echo esc_html($title_prefix . ' — ' . $city_name); ?></h2>
                <p class="ampi-city-altitude" data-ampi-altitude>Altitude de <?php echo esc_html($city_name); ?> : chargement…</p>
                <p class="ampi-meta" data-ampi-meta>Chargement du dernier run AROME-PI…</p>
            </div>
            <div class="ampi-badge">AROME-PI<br><strong>1,3 km</strong></div>
        </header>

        <div class="ampi-toolbar" <?php if (!$show_selector) : ?>hidden<?php endif; ?>>
            <div class="ampi-search">
                <label for="<?php echo esc_attr($input_id); ?>">Choisissez votre commune</label>
                <div class="ampi-search-control">
                    <span class="ampi-search-icon" aria-hidden="true">⌕</span>
                    <input
                        id="<?php echo esc_attr($input_id); ?>"
                        class="ampi-city-input"
                        type="search"
                        value="<?php echo esc_attr($city_name); ?>"
                        placeholder="Nom de commune ou code postal"
                        autocomplete="off"
                        spellcheck="false"
                        role="combobox"
                        aria-autocomplete="list"
                        aria-expanded="false"
                        aria-controls="<?php echo esc_attr($results_id); ?>"
                        aria-describedby="<?php echo esc_attr($status_id); ?>"
                    >
                </div>
                <button type="button" class="ampi-locate-button" data-ampi-locate>📍 Détecter ma ville</button>
                <div
                    id="<?php echo esc_attr($results_id); ?>"
                    class="ampi-search-results"
                    role="listbox"
                    hidden
                ></div>
                <p
                    id="<?php echo esc_attr($status_id); ?>"
                    class="ampi-search-status"
                    role="status"
                    aria-live="polite"
                >Saisissez au moins deux lettres ou un code postal.</p>
            </div>
            <div class="ampi-coverage">
                <strong>34 746 communes</strong>
                <span>Métropole et Corse</span>
            </div>
        </div>

        <p class="ampi-stale" data-ampi-stale role="status" hidden>
            Attention : la dernière mise à jour AROME-PI disponible a plus de 2 heures.
        </p>

        <div class="ampi-tabs" role="tablist" aria-label="Type de prévision AROME-PI">
            <button
                type="button"
                class="ampi-tab ampi-tab-map is-active"
                role="tab"
                aria-selected="true"
                data-ampi-tab="map-france"
            >Carte France</button>
            <button
                type="button"
                class="ampi-tab ampi-tab-map"
                role="tab"
                aria-selected="false"
                data-ampi-tab="map-europe"
            >Cartes Europe</button>
            <button
                type="button"
                class="ampi-tab"
                role="tab"
                aria-selected="false"
                data-ampi-tab="general"
            >Prévisions générales</button>
            <button
                type="button"
                class="ampi-tab ampi-tab-storm"
                role="tab"
                aria-selected="false"
                data-ampi-tab="storms"
            >Orages</button>
            <button
                type="button"
                class="ampi-tab ampi-tab-snow"
                role="tab"
                aria-selected="false"
                data-ampi-tab="snow"
            >Neige</button>
            <button
                type="button"
                class="ampi-tab ampi-tab-static"
                role="tab"
                aria-selected="false"
                data-ampi-tab="static"
            >Cartes fixes</button>
        </div>

        <div class="ampi-panel ampi-map-panel" data-ampi-panel="map-france">
            <?php
            echo ampi_render_map_shortcode(
                array(
                    'variable' => 'temperature',
                    'hauteur' => '1050',
                    'titre' => 'Cartes AROME-PI France — résolution 1,3 km',
                    'animation' => 'oui',
                    'vue' => 'france',
                )
            );
            ?>
        </div>

        <div class="ampi-panel ampi-map-panel" data-ampi-panel="map-europe" hidden>
            <?php
            echo ampi_render_map_shortcode(
                array(
                    'variable' => 'pression',
                    'hauteur' => '1050',
                    'titre' => 'Cartes AROME-PI Europe occidentale',
                    'animation' => 'oui',
                    'vue' => 'europe',
                )
            );
            ?>
        </div>

        <div class="ampi-panel" data-ampi-panel="general" hidden>
            <div class="ampi-table-wrap ampi-general-wrap" role="region" aria-label="Prévisions horaires générales" tabindex="0">
                <table class="ampi-table">
                    <thead>
                        <tr>
                            <th scope="col">Date</th>
                            <th scope="col">Heure</th>
                            <th scope="col">Temps</th>
                            <th scope="col">T°</th>
                            <th scope="col">Hum.</th>
                            <th scope="col">Pluie</th>
                            <th scope="col">Nuages</th>
                            <th scope="col">Vent</th>
                            <th scope="col">Rafales</th>
                            <th scope="col">Pression</th>
                        </tr>
                    </thead>
                    <tbody data-ampi-body-general>
                        <tr>
                            <td colspan="10" class="ampi-loading">Chargement des prévisions…</td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <section class="ampi-charts" data-ampi-charts aria-label="Diagrammes AROME-PI">
                <article class="ampi-chart-card">
                    <h3 data-ampi-chart-title-temperature>Diagramme températures (°C)</h3>
                    <div class="ampi-chart" data-ampi-chart-temperature></div>
                </article>
                <article class="ampi-chart-card">
                    <h3 data-ampi-chart-title-pressure>Diagramme pression ramenée au niveau de la mer (hPa)</h3>
                    <div class="ampi-chart" data-ampi-chart-pressure></div>
                </article>
                <article class="ampi-chart-card">
                    <h3 data-ampi-chart-title-rain>Diagramme précipitations (mm)</h3>
                    <p class="ampi-chart-total" data-ampi-rain-total>Précipitations cumulées : —</p>
                    <div class="ampi-chart" data-ampi-chart-rain></div>
                </article>
                <article class="ampi-chart-card">
                    <h3 data-ampi-chart-title-wind>Diagramme rafales et vent moyen</h3>
                    <div class="ampi-chart" data-ampi-chart-wind></div>
                </article>
            </section>
        </div>

        <div class="ampi-panel" data-ampi-panel="storms" hidden>
            <p class="ampi-storm-summary" data-ampi-storm-summary>
                Diagnostic convectif AROME-PI 0,01° : chargement…
            </p>
            <div class="ampi-top-scroll" data-ampi-top-scroll="storms" aria-label="Navigation horizontale du tableau orages" hidden><div></div></div>
            <div class="ampi-table-wrap ampi-storm-wrap" data-ampi-scroll-wrap="storms" role="region" aria-label="Prévisions horaires d'orages" tabindex="0">
                <table class="ampi-table ampi-storm-table">
                    <thead>
                        <tr>
                            <th scope="col">Date</th>
                            <th scope="col">Heure</th>
                            <th scope="col">Risque orage</th>
                            <th scope="col">MUCAPE</th>
                            <th scope="col">LCL estimé</th>
                            <th scope="col">Foudre</th>
                            <th scope="col">Grêle</th>
                            <th scope="col">Pluie conv.</th>
                            <th scope="col">Graupel</th>
                            <th scope="col">Pluie 1 h</th>
                            <th scope="col">Rafales</th>
                            <th scope="col">Type</th>
                            <th scope="col">Détails</th>
                        </tr>
                    </thead>
                    <tbody data-ampi-body-storms>
                        <tr>
                            <td colspan="13" class="ampi-loading">Chargement du diagnostic orageux…</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            <p class="ampi-storm-note">
                <strong>Lecture expert :</strong> la MUCAPE et la réflectivité maximale sont des sorties directes AROME-PI. Le risque, la foudre, la grêle et le type d’orage sont des diagnostics dérivés clairement signalés ; aucune valeur indisponible n’est inventée.
            </p>
        </div>

        <div class="ampi-panel" data-ampi-panel="snow" hidden>
            <p class="ampi-snow-summary" data-ampi-snow-summary>
                Diagnostic neige AROME-PI 0,01° : chargement…
            </p>
            <div class="ampi-top-scroll" data-ampi-top-scroll="snow" aria-label="Navigation horizontale du tableau neige" hidden><div></div></div>
            <div class="ampi-table-wrap ampi-snow-wrap" data-ampi-scroll-wrap="snow" role="region" aria-label="Risque horaire de neige" tabindex="0">
                <table class="ampi-table ampi-snow-table">
                    <thead>
                        <tr>
                            <th scope="col">Date</th>
                            <th scope="col">Heure</th>
                            <th scope="col">Risque neige</th>
                            <th scope="col">Phase</th>
                            <th scope="col">Neige 1 h</th>
                            <th scope="col">Neige 3 h</th>
                            <th scope="col">Neige 6 h</th>
                            <th scope="col">Tenue</th>
                            <th scope="col">Pres. hPa</th>
                            <th scope="col">Hum.</th>
                            <th scope="col">Vent moy. / raf.</th>
                            <th scope="col">Cumul neige fraîche</th>
                            <th scope="col">Détails</th>
                        </tr>
                    </thead>
                    <tbody data-ampi-body-snow>
                        <tr>
                            <td colspan="13" class="ampi-loading">Chargement du risque de neige…</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            <p class="ampi-snow-note">
                <strong>Lecture neige :</strong> les cumuls de neige sont des sorties directes AROME-PI. La neige fraîche et la tenue sont estimées à partir du cumul en eau, de la température à 2 m et de l’altitude du point de grille.
            </p>
        </div>

        <div class="ampi-panel ampi-static-panel" data-ampi-panel="static" hidden>
            <header class="ampi-static-head">
                <div>
                    <p class="ampi-kicker">CARTES PRÊTES À CONSULTER</p>
                    <h2>Cartes AROME-PI non interactives</h2>
                </div>
                <p>Présentation fixe avec le run, l’échéance et une carte lisible, dans l’esprit de votre exemple.</p>
            </header>
            <div class="ampi-static-gallery" data-ampi-static-gallery>
                <p class="ampi-loading">Chargement des cartes fixes…</p>
            </div>
        </div>

        <footer class="ampi-footer">
            <span data-ampi-generated>Mise à jour en cours de lecture…</span>
            <span>
                Données météo directes :
                <a href="https://www.data.gouv.fr/dataservices/api-modele-arome-prevision-immediate" target="_blank" rel="noopener noreferrer">API AROME Prévision Immédiate — Météo-France</a>
                • Recherche des communes :
                <a href="https://geo.api.gouv.fr/decoupage-administratif/communes" target="_blank" rel="noopener noreferrer">API officielle française</a>
                • <a href="https://www.alertes-meteo.com/" target="_blank" rel="noopener noreferrer">www.alertes-meteo.com</a>
            </span>
            <span class="ampi-plugin-version">Module AROME-PI v<?php echo esc_html(AMPI_VERSION); ?> (<?php echo esc_html(AMPI_RELEASE_DATE); ?>)</span>
        </footer>

        <noscript>
            <p class="ampi-message ampi-error">JavaScript doit être activé pour rechercher une commune.</p>
        </noscript>
    </section>
    <?php
    return ob_get_clean();
}

