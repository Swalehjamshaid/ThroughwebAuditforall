
from __future__ import annotations

from typing import Dict, Any
from dataclasses import dataclass

@dataclass
class ScoreProfile:
    weights: Dict[str, float] = None
    def __post_init__(self):
        self.weights = self.weights or {
            'executive_summary': 0.10,
            'overall_site_health': 0.10,
            'crawlability_indexation': 0.20,
            'on_page_seo': 0.20,
            'performance_technical': 0.15,
            'mobile_security_international': 0.15,
            'competitor_analysis': 0.05,
            'broken_links_intelligence': 0.025,
            'opportunities_growth_roi': 0.025,
        }

def grade_to_letter(score: float) -> str:
    if score >= 95: return 'A+'
    if score >= 90: return 'A'
    if score >= 80: return 'B'
    if score >= 70: return 'C'
    return 'D'

def run_audit(url: str, profile: ScoreProfile | None = None) -> Dict[str, Any]:
    profile = profile or ScoreProfile()
    cat_scores = {'Crawlability': 78, 'On-Page SEO': 74, 'Performance': 80, 'Security': 88, 'Mobile': 83}
    overall = round(sum(cat_scores.values()) / len(cat_scores), 2)
    exec_summary = {
        'overall_site_health_score': overall,
        'website_grade': grade_to_letter(overall),
        'summary': ('Automated analysis across health, crawlability, SEO, performance, security & mobile. '
                    'Stable and secure, with improvement opportunities in structured data and image optimization.'),
        'strengths': ['HTTPS configured','Mobile friendly','Low 5xx errors'],
        'weak_areas': ['Missing structured data','Large images','Duplicate headings'],
        'priority_fixes': ['Compress images','Add schema.org','Consolidate duplicate H1/H2'],
        'category_breakdown': cat_scores,
    }
    overall_health = {
        'site_health_score': overall,
        'total_errors': 23,
        'total_warnings': 67,
        'total_notices': 120,
        'total_crawled_pages': 250,
        'total_indexed_pages': 220,
        'issues_trend': [12,16,10,8,6],
        'crawl_budget_efficiency': 0.86,
        'orphan_pages_pct': 3.2,
        'audit_completion_status': 'Complete',
    }
    crawlability_indexation = {
        'http_2xx_pages': 190, 'http_3xx_pages': 18, 'http_4xx_pages': 7, 'http_5xx_pages': 2,
        'redirect_chains': 3, 'redirect_loops': 0, 'broken_internal_links': 11, 'broken_external_links': 9,
        'robots_blocked_urls': 4, 'meta_robots_blocked_urls': 3, 'non_canonical_pages': 12, 'missing_canonical_tags': 15,
        'incorrect_canonical_tags': 2, 'sitemap_missing_pages': 6, 'sitemap_not_crawled_pages': 5, 'hreflang_errors': 0,
        'hreflang_conflicts': 0, 'pagination_issues': 2, 'crawl_depth_distribution': [60,120,70], 'duplicate_parameter_urls': 4,
    }
    on_page_seo = {
        'missing_title_tags': 8,'duplicate_title_tags': 4,'title_too_long': 9,'title_too_short': 3,
        'missing_meta_descriptions': 11,'duplicate_meta_descriptions': 6,'meta_too_long': 7,'meta_too_short': 5,
        'missing_h1': 2,'multiple_h1': 3,'duplicate_headings': 12,'thin_content_pages': 14,'duplicate_content_pages': 9,
        'low_text_to_html_ratio': 20,'missing_image_alt_tags': 22,'duplicate_alt_tags': 8,'large_uncompressed_images': 16,
        'pages_without_indexed_content': 5,'missing_structured_data': 17,'structured_data_errors': 6,'rich_snippet_warnings': 4,
        'missing_open_graph_tags': 13,'long_urls': 7,'uppercase_urls': 2,'non_seo_friendly_urls': 5,'too_many_internal_links': 9,
        'pages_without_incoming_links': 15,'orphan_pages': 8,'broken_anchor_links': 6,'redirected_internal_links': 7,
        'nofollow_internal_links': 3,'link_depth_issues': 4,'external_links_count': 420,'broken_external_links': 9,
        'anchor_text_issues': 10,
    }
    performance_technical = {
        'lcp': 2.8,'fcp': 1.2,'cls': 0.08,'total_blocking_time': 180,'first_input_delay': 18,'speed_index': 3.4,
        'time_to_interactive': 2.6,'dom_content_loaded': 1.0,'total_page_size_mb': 2.1,'requests_per_page': 54,
        'unminified_css': 2,'unminified_js': 3,'render_blocking_resources': 4,'excessive_dom_size': 0,
        'third_party_script_load': 12,'server_response_time_ms': 220,'image_optimization': 68,'lazy_loading_issues': 3,
        'browser_caching_issues': 5,'missing_compression': 1,'resource_load_errors': 0,
    }
    mobile_security_international = {
        'mobile_friendly_test': True,'viewport_meta_tag': True,'small_font_issues': 2,'tap_target_issues': 3,
        'mobile_core_web_vitals': {'lcp': 3.1,'cls': 0.1,'fid': 22},'mobile_layout_issues': 1,'intrusive_interstitials': 0,
        'mobile_navigation_issues': 1,'https_implementation': True,'ssl_certificate_validity_days': 320,'expired_ssl': False,
        'mixed_content': 0,'insecure_resources': 0,'missing_security_headers': 2,'open_directory_listing': 0,
        'login_pages_without_https': 0,'missing_hreflang': 4,'incorrect_language_codes': 0,'hreflang_conflicts': 0,
        'region_targeting_issues': 0,'multi_domain_seo_issues': 0,'domain_authority': 42,'referring_domains': 120,
        'total_backlinks': 2400,'toxic_backlinks': 35,'nofollow_backlinks': 1100,'anchor_distribution': {'branded': 0.6,'generic': 0.3,'exact': 0.1},
        'referring_ips': 90,'lost_new_backlinks': {'lost': 12,'new': 25},'javascript_rendering_issues': 0,'css_blocking': 2,
        'crawl_budget_waste': 4,'amp_issues': 0,'pwa_issues': 1,'canonical_conflicts': 1,'subdomain_duplication': 0,
        'pagination_conflicts': 0,'dynamic_url_issues': 2,'lazy_load_conflicts': 0,'sitemap_presence': True,'noindex_issues': 1,
        'structured_data_consistency': 72,'redirect_correctness': 95,'broken_rich_media': 0,'social_metadata_presence': 80,
        'error_trend': [4,3,2,2,1],'health_trend': [70,72,74,76,78],'crawl_trend': [200,220,240,230,250],
        'index_trend': [180,190,200,210,220],'core_web_vitals_trend': [68,70,72,75,77],'backlink_trend': [2100,2200,2300,2350,2400],
        'keyword_trend': [120,130,125,140,150],'historical_comparison': {'score_prev': 70, 'score_now': 78},
        'overall_stability_index': 82,
    }
    competitor_analysis = {
        'competitor_health_score': 75,
        'performance_comparison': {'you': 80, 'compA': 76, 'compB': 73},
        'core_web_vitals_comparison': {'you': 77, 'compA': 74, 'compB': 70},
        'seo_issues_comparison': {'you': 30, 'compA': 45, 'compB': 40},
        'broken_links_comparison': {'you': 9, 'compA': 14, 'compB': 11},
        'authority_score': 42,
        'backlink_growth': {'you': 25, 'compA': 10, 'compB': 15},
        'keyword_visibility': {'you': 150, 'compA': 120, 'compB': 140},
        'rank_distribution': {'top10': 20, 'top20': 35, 'top100': 90},
        'content_volume': {'you': 240, 'compA': 180, 'compB': 210},
        'speed_comparison': {'you': 3.4, 'compA': 4.0, 'compB': 3.8},
        'mobile_score': {'you': 83, 'compA': 77, 'compB': 79},
        'security_score': {'you': 88, 'compA': 80, 'compB': 82},
        'competitive_gap_score': 68,
        'opportunity_heatmap': [[3,2,1],[2,3,2],[1,2,3]],
        'risk_heatmap': [[1,2,3],[2,2,2],[3,2,1]],
        'overall_competitive_rank': 2,
    }
    broken_links_intelligence = {
        'total_broken_links': 18,'internal_broken_links': 11,'external_broken_links': 7,
        'broken_links_trend': [9,11,10,12,8],'broken_pages_by_impact': {'critical': 3,'high': 5,'medium': 6,'low': 4},
        'status_code_distribution': {'200': 190,'301': 18,'404': 7,'500': 2},
        'page_type_distribution': {'blog': 40,'product': 30,'docs': 20,'other': 10},
        'fix_priority_score': 72,'seo_loss_impact': 61,'affected_pages_count': 22,'broken_media_links': 2,
        'resolution_progress': 24,'risk_severity_index': 68,
    }
    opportunities_growth_roi = {
        'high_impact_opportunities': 12,'quick_wins_score': 74,'long_term_fixes': 8,'traffic_growth_forecast': 15,
        'ranking_growth_forecast': 12,'conversion_impact_score': 9,'content_expansion_opportunities': 20,
        'internal_linking_opportunities': 14,'speed_improvement_potential': 18,'mobile_improvement_potential': 12,
        'security_improvement_potential': 10,'structured_data_opportunities': 16,'crawl_optimization_potential': 14,
        'backlink_opportunity_score': 19,'competitive_gap_roi': 13,'fix_roadmap_timeline_weeks': 8,
        'time_to_fix_estimate_weeks': 6,'cost_to_fix_estimate_k': 20,'roi_forecast': 1.8,
        'overall_growth_readiness': 76,
    }
    category_scores = {
        'executive_summary': exec_summary['overall_site_health_score'],
        'overall_site_health': overall_health['site_health_score'],
        'crawlability_indexation': 78,
        'on_page_seo': 74,
        'performance_technical': 80,
        'mobile_security_international': 83,
        'competitor_analysis': competitor_analysis['competitor_health_score'],
        'broken_links_intelligence': 100 - broken_links_intelligence['risk_severity_index'],
        'opportunities_growth_roi': opportunities_growth_roi['overall_growth_readiness'],
    }
    weights = ScoreProfile().weights
    overall_score = sum(category_scores[k] * weights[k] for k in category_scores)
    charts = {
        'trend': {'labels': ['Jan','Feb','Mar','Apr','May','Jun'], 'values': [4,6,3,8,7,9]},
        'severity': {'labels': ['Critical','High','Medium','Low'], 'values': [5,12,20,8]},
        'top_owners': {'labels': ['Ops','IT','Finance','HR'], 'values': [22,18,12,9]},
        'status': {'labels': ['Week 1','Week 2','Week 3','Week 4'], 'open': [8,6,7,4], 'closed': [2,4,5,8]},
        'aging': {'labels': ['0-7','8-14','15-30','31+'], 'values': [5,7,12,9]},
    }
    return {
        'url': url,
        'executive_summary': exec_summary,
        'overall_site_health': overall_health,
        'crawlability_indexation': crawlability_indexation,
        'on_page_seo': on_page_seo,
        'performance_technical': performance_technical,
        'mobile_security_international': mobile_security_international,
        'competitor_analysis': competitor_analysis,
        'broken_links_intelligence': broken_links_intelligence,
        'opportunities_growth_roi': opportunities_growth_roi,
        'overall_score': round(overall_score, 2),
        'overall_grade': grade_to_letter(overall_score),
        'charts': charts,
        'category_scores': category_scores,
    }
