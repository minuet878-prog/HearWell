# #126 舊 `styles.css` 選擇器對照清單

舊檔：`feat/tailwind-migration`（`8716467`）的 `screening/static/screening/styles.css`；新檔：`frontend/src/site.css`。

產生方式：用 postcss 把兩份 CSS 拆成「所在的 media query ＋ 單一選擇器 → 每個屬性的值」，把新檔的 `var(--token)` 換回主題設定的數值（`.5rem` 視同 `0.5rem`）後逐一比較，也檢查新檔沒有多出舊檔沒有的屬性。一個舊規則有多個選擇器（例如 `.link-card:hover, .link-card:active`）時拆成多列，所以共 176 列。

- 「相同」：新定義在 `site.css` 最後一個 `@layer components` 區塊（#126），選擇器、所在 media query、屬性與數值都相同。
- 「已由前票接手」：#124、#125 已定義，數值見各自的驗證紀錄與瀏覽器測試。
- 「沒搬」：沒有任何模板、React、Python 用到。

| 舊選擇器（含 media query） | 新定義 | 結果 |
|---|---|---|
| `html` | #124 基礎層 `html { font-size: var(--root-font-size) }`（112.5%） | 已由前票接手，瀏覽器測試量過 |
| `:root` | #124 主題 token（`--font-sans`、`--color-body`、`--color-primary`、`--color-primary-hover`、`--color-focus-ring` 等） | 已由前票接手，瀏覽器測試量過 |
| `.text-success` | — | 沒搬：模板、React、Python 都沒用到 |
| `.text-warning` | — | 沒搬：模板、React、Python 都沒用到 |
| `.text-danger` | #126 區塊，引用 `--color-severe` | 相同（1 個屬性） |
| `.text-secondary` | — | 沒搬：模板、React、Python 都沒用到 |
| `.btn-primary` | #125 `.btn-primary`（主色、hover #173b6a、active #122f55、停用主色、焦點光暈主色 0.5） | 已由前票接手，瀏覽器測試量過 |
| `.btn-outline-primary` | #125 `.btn-outline-primary`（同舊覆寫的九個值） | 已由前票接手，瀏覽器測試量過 |
| `.container` | #124 `@utility container`（`max-width: var(--container-content)` = 40rem） | 已由前票接手，瀏覽器測試量過 |
| `.btn` | #125 `.btn`（`min-height`／`min-width: var(--spacing-touch)`、`border-radius: var(--radius-button)`） | 已由前票接手，瀏覽器測試量過 |
| `.form-control:focus` | #125 `.form-control:focus`（外框主色、`--shadow-input-focus`） | 已由前票接手，瀏覽器測試量過 |
| `.skip-link` | #126 區塊，引用 `--color-primary` | 相同（8 個屬性） |
| `.site-header` | #126 區塊，引用 `--color-primary` | 相同（2 個屬性） |
| `.site-header-bar` | #126 區塊 | 相同（5 個屬性） |
| `.site-header-bar .site-account` | #126 區塊 | 相同（2 個屬性） |
| `@media (min-width: 48em) .site-header-bar .site-account` | #126 區塊 | 相同（4 個屬性） |
| `.site-brand` | #126 區塊 | 相同（3 個屬性） |
| `.site-brand a` | #126 區塊 | 相同（2 個屬性） |
| `.site-back` | #126 區塊，引用 `--spacing-touch` | 相同（4 個屬性） |
| `.pwa-pull` | #126 區塊，引用 `--color-pull`、`--color-primary` | 相同（11 個屬性） |
| `.site-nav` | #126 區塊 | 相同（1 個屬性） |
| `.site-nav ul` | #126 區塊 | 相同（4 個屬性） |
| `.site-nav a` | #126 區塊，引用 `--spacing-touch`、`--color-heading` | 相同（10 個屬性） |
| `.site-nav a[aria-current="page"]` | #126 區塊，引用 `--color-primary` | 相同（1 個屬性） |
| `.site-nav svg` | #126 區塊 | 相同（8 個屬性） |
| `@media (min-width: 48em) .site-nav` | #126 區塊，引用 `--color-border-strong` | 相同（1 個屬性） |
| `@media (min-width: 48em) .site-nav ul` | #126 區塊 | 相同（1 個屬性） |
| `@media (min-width: 48em) .site-nav a[aria-current="page"]` | #126 區塊，引用 `--color-primary` | 相同（1 個屬性） |
| `@media (max-width: 47.99em) .site-nav` | #126 區塊，引用 `--color-border-strong` | 相同（7 個屬性） |
| `@media (max-width: 47.99em) .site-nav ul` | #126 區塊 | 相同（1 個屬性） |
| `@media (max-width: 47.99em) .site-nav li` | #126 區塊 | 相同（2 個屬性） |
| `@media (max-width: 47.99em) .site-nav a` | #126 區塊 | 相同（5 個屬性） |
| `@media (max-width: 47.99em) .site-nav a[aria-current="page"]` | #126 區塊，引用 `--color-primary` | 相同（1 個屬性） |
| `.site-footer` | #126 區塊，引用 `--color-surface`、`--color-footer` | 相同（4 個屬性） |
| `@media (max-width: 47.99em) .site-footer` | #126 區塊 | 相同（1 個屬性） |
| `.site-footer a` | #126 區塊，引用 `--color-primary` | 相同（3 個屬性） |
| `.site-footer-links` | #126 區塊 | 相同（6 個屬性） |
| `.site-footer-links a` | #126 區塊，引用 `--spacing-touch` | 相同（3 個屬性） |
| `.site-footer p` | #126 區塊 | 相同（2 個屬性） |
| `.level-badge` | #126 區塊，引用 `--radius-badge` | 相同（5 個屬性） |
| `.level-badge-normal` | #126 區塊，引用 `--color-normal-bg`、`--color-normal` | 相同（2 個屬性） |
| `.level-badge-mild_to_moderate` | #126 區塊，引用 `--color-mild-bg`、`--color-mild` | 相同（2 個屬性） |
| `.level-badge-severe` | #126 區塊，引用 `--color-severe-bg`、`--color-severe` | 相同（2 個屬性） |
| `.level-badge-unknown` | #126 區塊，引用 `--color-surface`、`--color-body` | 相同（2 個屬性） |
| `.link-card` | #126 區塊，引用 `--color-border`、`--radius-card`、`--shadow-card` | 相同（11 個屬性） |
| `.link-card:hover` | #126 區塊，引用 `--color-primary`、`--color-brand-soft` | 相同（3 個屬性） |
| `.link-card:active` | #126 區塊，引用 `--color-primary`、`--color-brand-soft` | 相同（3 個屬性） |
| `.link-card:focus-visible` | #126 區塊，引用 `--color-primary` | 相同（2 個屬性） |
| `.link-card-body` | #126 區塊 | 相同（5 個屬性） |
| `.link-card-title` | #126 區塊，引用 `--color-primary` | 相同（3 個屬性） |
| `.link-card-arrow` | #126 區塊，引用 `--color-primary` | 相同（3 個屬性） |
| `.narrow-form` | #126 區塊，引用 `--container-form` | 相同（2 個屬性） |
| `div.choice-group` | #126 區塊 | 相同（3 個屬性） |
| `div.choice-group label` | #126 區塊，引用 `--color-border`、`--radius-button`、`--color-heading` | 相同（10 個屬性） |
| `div.choice-group input` | #126 區塊，引用 `--color-primary` | 相同（3 個屬性） |
| `div.choice-group label:has(input:checked)` | #126 區塊，引用 `--color-primary`、`--color-brand-selected` | 相同（4 個屬性） |
| `div.choice-group label:focus-within` | #126 區塊，引用 `--color-primary` | 相同（2 個屬性） |
| `.trend-summary` | #126 區塊，引用 `--color-primary`、`--radius-card`、`--color-brand-selected`、`--color-heading` | 相同（5 個屬性） |
| `.trend-summary-score strong` | #126 區塊，引用 `--color-primary` | 相同（2 個屬性） |
| `.trend-summary-score span` | #126 區塊 | 相同（1 個屬性） |
| `.home-band` | #126 區塊，引用 `--color-brand-soft`、`--radius-band` | 相同（4 個屬性） |
| `.home-illustration` | #126 區塊，引用 `--color-primary` | 相同（9 個屬性） |
| `.step-cards` | #126 區塊 | 相同（6 個屬性） |
| `.step-cards li` | #126 區塊，引用 `--color-border-subtle`、`--radius-card` | 相同（7 個屬性） |
| `.step-number` | #126 區塊，引用 `--color-primary` | 相同（9 個屬性） |
| `.step-icon` | #126 區塊，引用 `--color-primary` | 相同（7 個屬性） |
| `.result-preview` | #126 區塊，引用 `--color-border-strong`、`--radius-card` | 相同（5 個屬性） |
| `.result-preview .result-level` | #126 區塊 | 相同（1 個屬性） |
| `.preview-tag` | #126 區塊，引用 `--radius-badge`、`--color-body` | 相同（8 個屬性） |
| `.ioi-note` | #126 區塊，引用 `--color-brand-soft`、`--color-primary`、`--radius-small` | 相同（5 個屬性） |
| `.question-progress` | #126 區塊，引用 `--color-body` | 相同（3 個屬性） |
| `.answer-app legend:focus` | #126 區塊，引用 `--color-primary` | 相同（2 個屬性） |
| `.answer-nav` | #126 區塊 | 相同（3 個屬性） |
| `.answer-loading #answer-form` | #126 區塊 | 相同（1 個屬性） |
| `#answer-loading:empty` | #126 區塊 | 相同（1 個屬性） |
| `.result-banner` | #126 區塊，引用 `--radius-button` | 相同（3 個屬性） |
| `.result-banner > div:not(.result-level)` | #126 區塊，引用 `--color-heading` | 相同（1 個屬性） |
| `.result-level` | #126 區塊 | 相同（3 個屬性） |
| `.result-banner-normal` | #126 區塊，引用 `--color-normal-bg`、`--color-normal` | 相同（2 個屬性） |
| `.result-banner-mild_to_moderate` | #126 區塊，引用 `--color-mild-bg`、`--color-mild` | 相同（2 個屬性） |
| `.result-banner-severe` | #126 區塊，引用 `--color-severe-bg`、`--color-severe` | 相同（2 個屬性） |
| `.result-banner-unknown` | #126 區塊，引用 `--color-surface`、`--color-body` | 相同（2 個屬性） |
| `details summary` | #126 區塊，引用 `--spacing-touch`、`--color-primary` | 相同（4 個屬性） |
| `.history-tabs` | #126 區塊 | 相同（4 個屬性） |
| `.history-tabs a` | #126 區塊，引用 `--spacing-touch`、`--color-primary`、`--radius-tab` | 相同（10 個屬性） |
| `.history-tabs a[aria-current="page"]` | #126 區塊，引用 `--color-primary` | 相同（2 個屬性） |
| `.aided-difference` | #126 區塊，引用 `--color-primary`、`--radius-button`、`--color-brand-selected`、`--color-heading` | 相同（6 個屬性） |
| `.trend-legend` | #126 區塊，引用 `--color-heading` | 相同（7 個屬性） |
| `.trend-legend li` | #126 區塊 | 相同（3 個屬性） |
| `.trend-bands` | #126 區塊 | 相同（7 個屬性） |
| `.trend-bands li` | #126 區塊 | 相同（3 個屬性） |
| `.trend-band-swatch` | #126 區塊，引用 `--color-border-strong`、`--radius-small` | 相同（5 個屬性） |
| `.ioi-columns` | #126 區塊 | 相同（6 個屬性） |
| `.ioi-grid` | #126 區塊 | 相同（4 個屬性） |
| `.ioi-line` | #126 區塊，引用 `--color-border` | 相同（3 個屬性） |
| `.ioi-axis .ioi-grid` | #126 區塊，引用 `--color-heading` | 相同（2 個屬性） |
| `.ioi-axis .ioi-line` | #126 區塊 | 相同（1 個屬性） |
| `.ioi-grid > *` | #126 區塊 | 相同（1 個屬性） |
| `.ioi-band` | #126 區塊，引用 `--color-input-border`、`--radius-small`、`--color-border` | 相同（5 個屬性） |
| `.ioi-legend-band` | #126 區塊，引用 `--color-input-border`、`--radius-small`、`--color-border` | 相同（7 個屬性） |
| `.ioi-dot` | #126 區塊 | 相同（3 個屬性） |
| `.ioi-legend-latest` | #126 區塊，引用 `--color-primary` | 相同（5 個屬性） |
| `.ioi-dot-latest` | #126 區塊，引用 `--color-primary` | 相同（2 個屬性） |
| `.ioi-diamond` | #126 區塊，引用 `--color-body` | 相同（5 個屬性） |
| `.ioi-legend-previous` | #126 區塊，引用 `--color-body` | 相同（5 個屬性） |
| `.ioi-dot-previous` | #126 區塊 | 相同（1 個屬性） |
| `.ioi-dot-previous + .ioi-dot-latest` | #126 區塊 | 相同（1 個屬性） |
| `.ioi-name` | #126 區塊，引用 `--color-heading` | 相同（5 個屬性） |
| `.audiogram-chart` | #126 區塊 | 相同（2 個屬性） |
| `.audiogram-svg` | #126 區塊 | 相同（4 個屬性） |
| `.audiogram-symbols` | #126 區塊 | 相同（4 個屬性） |
| `.audiogram-symbol` | #126 區塊，引用 `--spacing-touch`、`--color-input-border` | 相同（5 個屬性） |
| `.audiogram-symbol.ear-right` | #126 區塊，引用 `--color-ear-right` | 相同（1 個屬性） |
| `.audiogram-symbol.ear-left` | #126 區塊，引用 `--color-ear-left` | 相同（1 個屬性） |
| `.audiogram-symbol[aria-pressed="true"]` | #126 區塊，引用 `--color-primary`、`--color-brand-selected` | 相同（3 個屬性） |
| `.audiogram-table-grid` | #126 區塊 | 相同（3 個屬性） |
| `.ear-results` | #126 區塊 | 相同（3 個屬性） |
| `.ear-result.ear-right` | #126 區塊，引用 `--color-ear-right` | 相同（1 個屬性） |
| `.ear-result.ear-left` | #126 區塊，引用 `--color-ear-left` | 相同（1 個屬性） |
| `.audiogram-plot` | #126 區塊 | 相同（1 個屬性） |
| `.audiogram-magnifier` | #126 區塊，引用 `--color-heading`、`--radius-field` | 相同（9 個屬性） |
| `.audiogram-magnifier[data-place="above"]` | #126 區塊 | 相同（1 個屬性） |
| `.audiogram-magnifier[data-place="beside"][data-side="right"]` | #126 區塊 | 相同（1 個屬性） |
| `.audiogram-magnifier[data-place="beside"][data-side="left"]` | #126 區塊 | 相同（1 個屬性） |
| `.audiogram-mask-switch` | #126 區塊，引用 `--color-input-border`、`--color-heading` | 相同（4 個屬性） |
| `.audiogram-mask-switch.on` | #126 區塊，引用 `--color-masking` | 相同（3 個屬性） |
| `.audiogram-mask-switch.on:hover` | #126 區塊，引用 `--color-masking` | 相同（3 個屬性） |
| `.audiogram-chart.masking` | #126 區塊，引用 `--color-masking` | 相同（2 個屬性） |
| `.compare-legend` | #126 區塊 | 相同（4 個屬性） |
| `.compare-line` | #126 區塊，引用 `--color-ear-right` | 相同（5 個屬性） |
| `.compare-line.old` | #126 區塊，引用 `--color-ear-right-old` | 相同（1 個屬性） |
| `.compare-legend-left .compare-line` | #126 區塊，引用 `--color-ear-left` | 相同（1 個屬性） |
| `.compare-legend-left .compare-line.old` | #126 區塊，引用 `--color-ear-left-old` | 相同（1 個屬性） |
| `.health-report section` | #126 區塊 | 相同（1 個屬性） |
| `.report-meta` | #126 區塊 | 相同（3 個屬性） |
| `.report-handwrite span` | #126 區塊 | 相同（3 個屬性） |
| `.report-summary` | #126 區塊，引用 `--color-heading`、`--radius-button` | 相同（3 個屬性） |
| `.report-score` | #126 區塊 | 相同（2 個屬性） |
| `.health-report .table` | #126 區塊 | 相同（2 個屬性） |
| `.report-level` | #126 區塊，引用 `--radius-small` | 相同（4 個屬性） |
| `.report-disclaimer` | #126 區塊，引用 `--color-input-border` | 相同（3 個屬性） |
| `@media print @page` | #126，放在圖層外（`@page` 是頁面規則） | 相同（1 個屬性） |
| `@media print .health-report *` | #126 區塊 | 相同（1 個屬性） |
| `@media print body:has(.health-report) .site-header` | #126 區塊 | 相同（1 個屬性） |
| `@media print body:has(.health-report) .site-nav` | #126 區塊 | 相同（1 個屬性） |
| `@media print body:has(.health-report) footer` | #126 區塊 | 相同（1 個屬性） |
| `@media print .health-report .no-print` | #126 區塊 | 相同（1 個屬性） |
| `@media print body:has(.health-report)` | #126 區塊 | 相同（1 個屬性） |
| `@media print .health-report section` | #126 區塊 | 相同（2 個屬性） |
| `@media print .health-report .report-part` | #126 區塊 | 相同（1 個屬性） |
| `@media print .health-report .report-part > h2` | #126 區塊 | 相同（1 個屬性） |
| `@media print .report-disclaimer` | #126 區塊 | 相同（1 個屬性） |
| `@media print .health-report .table > :not(caption) > * > *` | #126 區塊 | 相同（1 個屬性） |
| `@media print .health-report .audiogram-chart` | #126 區塊 | 相同（1 個屬性） |
| `.account-details` | #126 區塊 | 相同（3 個屬性） |
| `.account-details dd` | #126 區塊 | 相同（2 個屬性） |
| `.account-danger` | #126 區塊，引用 `--color-severe` | 相同（1 個屬性） |
| `.site-account` | #126 區塊 | 相同（1 個屬性） |
| `.site-account:hover` | #126 區塊 | 相同（1 個屬性） |
| `.questionnaire-guide` | #126 區塊，引用 `--color-primary`、`--radius-card`、`--color-brand-soft`、`--color-heading` | 相同（5 個屬性） |
| `.questionnaire-icon` | #126 區塊，引用 `--color-brand-soft` | 相同（8 個屬性） |
| `.link-card:hover .questionnaire-icon` | #126 區塊 | 相同（1 個屬性） |
| `.link-card:active .questionnaire-icon` | #126 區塊 | 相同（1 個屬性） |
| `.questionnaire-icon svg` | #126 區塊，引用 `--color-primary` | 相同（7 個屬性） |
| `.card-tags` | #126 區塊 | 相同（3 個屬性） |
| `.card-tag` | #126 區塊，引用 `--radius-badge`、`--color-surface`、`--color-footer` | 相同（5 個屬性） |
| `.audiogram-thumbnail` | #126 區塊，引用 `--color-border`、`--radius-small` | 相同（6 個屬性） |
| `.ssq-scale input[type="range"]` | #126 區塊，引用 `--spacing-touch`、`--color-primary` | 相同（3 個屬性） |
| `.ssq-scale > label:last-child` | #126 區塊，引用 `--spacing-touch` | 相同（4 個屬性） |
| `@media (max-width: 35em) .questionnaire-card` | #126 區塊 | 相同（1 個屬性） |
| `@media (max-width: 35em) .questionnaire-card .link-card-body` | #126 區塊 | 相同（2 個屬性） |
| `@media (max-width: 35em) .questionnaire-card .link-card-arrow` | #126 區塊 | 相同（1 個屬性） |
| `.comparison-items` | #126 區塊 | 相同（1 個屬性） |
| `.report-answers` | #126 區塊 | 相同（1 個屬性） |
| `@media print .health-report .report-answers > ol` | #126 區塊 | 相同（1 個屬性） |
| `@media print .health-report .report-answers::details-content` | #126 區塊 | 相同（1 個屬性） |
