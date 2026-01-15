from dataclasses import dataclass
from typing import Any

# Full registry map 1..200 categorized; keys are canonical metric keys
EXECUTIVE = {
    1: 'overall_site_health_score', 2: 'website_grade', 3: 'executive_summary',
    4: 'strengths', 5: 'weaknesses', 6: 'priority_fixes', 7: 'severity_indicators',
    8: 'category_breakdown', 9: 'presentation_standard', 10: 'export_readiness',
}
OVERALL = {i: k for i,k in zip(range(11,21), [
    'site_health_score','total_errors','total_warnings','total_notices','total_crawled_pages',
    'total_indexed_pages','issues_trend','crawl_budget_efficiency','orphan_pages_pct','audit_completion_status'
])}
CRAWLABILITY = {i: k for i,k in zip(range(21,41), [
    'http_2xx','http_3xx','http_4xx','http_5xx','redirect_chains','redirect_loops','broken_internal_links',
    'broken_external_links','robots_blocked','meta_robots_blocked','non_canonical_pages','missing_canonical',
    'incorrect_canonical','sitemap_missing_pages','sitemap_not_crawled','hreflang_errors','hreflang_conflicts',
    'pagination_issues','crawl_depth_distribution','duplicate_param_urls'
])}
ONPAGE = {i: k for i,k in zip(range(41,76), [
    'missing_title','duplicate_title','title_too_long','title_too_short','missing_meta_desc','duplicate_meta_desc',
    'meta_too_long','meta_too_short','missing_h1','multiple_h1','duplicate_headings','thin_content','duplicate_content',
    'low_text_html_ratio','missing_img_alt','duplicate_img_alt','large_uncompressed_images','pages_without_indexed_content',
    'missing_structured_data','structured_data_errors','rich_snippet_warnings','missing_og_tags','long_urls','uppercase_urls',
    'non_seo_friendly_urls','too_many_internal_links','pages_without_incoming_links','orphan_pages','broken_anchor_links',
    'redirected_internal_links','nofollow_internal_links','link_depth_issues','external_links_count','broken_external_links_onpage',
    'anchor_text_issues'
])}
PERF = {i: k for i,k in zip(range(76,97), [
    'lcp','fcp','cls','total_blocking_time','first_input_delay','speed_index','tti','dom_content_loaded','total_page_size',
    'requests_per_page','unminified_css','unminified_js','render_blocking','excessive_dom','third_party_script_load',
    'server_response_time','image_optimization','lazy_loading_issues','browser_caching_issues','missing_compression','resource_load_errors'
])}
MOBILE_SECURITY_INTL = {i: k for i,k in zip(range(97,151), [
    'mobile_friendly','viewport_meta','small_font_issues','tap_target_issues','mobile_core_web_vitals','mobile_layout_issues',
    'intrusive_interstitials','mobile_nav_issues','https_implementation','ssl_validity','expired_ssl','mixed_content','insecure_resources',
    'missing_security_headers','open_directory_listing','login_without_https','missing_hreflang','incorrect_language_codes',
    'hreflang_conflicts_intl','region_target_issues','multi_domain_seo_issues','domain_authority','referring_domains','total_backlinks',
    'toxic_backlinks','nofollow_backlinks','anchor_distribution','referring_ips','lost_new_backlinks','js_rendering_issues','css_blocking',
    'crawl_budget_waste','amp_issues','pwa_issues','canonical_conflicts','subdomain_duplication','pagination_conflicts','dynamic_url_issues',
    'lazy_load_conflicts','sitemap_presence','noindex_issues','structured_data_consistency','redirect_correctness','broken_rich_media',
    'social_metadata_presence','error_trend','health_trend','crawl_trend','index_trend','cwv_trend','backlink_trend','keyword_trend',
    'historical_comparison','overall_stability_index'
])}
COMPETITOR = {i: k for i,k in zip(range(151,168), [
    'competitor_health_score','competitor_performance_comparison','competitor_cwv_comparison','competitor_seo_issues_comparison',
    'competitor_broken_links','competitor_authority_score','competitor_backlink_growth','competitor_keyword_visibility',
    'competitor_rank_distribution','competitor_content_volume','competitor_speed_comparison','competitor_mobile_score',
    'competitor_security_score','competitive_gap_score','competitive_opportunity_heatmap','competitive_risk_heatmap',
    'overall_competitive_rank'
])}
BROKEN = {i: k for i,k in zip(range(168,181), [
    'total_broken_links','internal_broken_links','external_broken_links','broken_links_trend','broken_pages_by_impact','status_code_distribution',
    'page_type_distribution','fix_priority_score','seo_loss_impact','affected_pages_count','broken_media_links','resolution_progress','risk_severity_index'
])}
OPPS = {i: k for i,k in zip(range(181,201), [
    'high_impact_opportunities','quick_wins_score','long_term_fixes','traffic_growth_forecast','ranking_growth_forecast','conversion_impact_score',
    'content_expansion_opportunities','internal_linking_opportunities','speed_improvement_potential','mobile_improvement_potential',
    'security_improvement_potential','structured_data_opportunities','crawl_optimization_potential','backlink_opportunity_score',
    'competitive_gap_roi','fix_roadmap_timeline','time_to_fix_estimate','cost_to_fix_estimate','roi_forecast','overall_growth_readiness'
])}

ALL = {}
for group in [EXECUTIVE, OVERALL, CRAWLABILITY, ONPAGE, PERF, MOBILE_SECURITY_INTL, COMPETITOR, BROKEN, OPPS]:
    ALL.update(group)

@dataclass
class MetricResult:
    key: str
    value: Any
    score: float
    details: Any = None