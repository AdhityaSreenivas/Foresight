"""
PSIF Platform — Methodology Disclosure Template Tags

Usage in Django templates:
    {% load methodology_tags %}

    {# Full notice banner / card #}
    {% methodology_notice "iogp" %}
    {% methodology_notice "psif_model" compact=True %}

    {# Inline indicator / badge with tooltip #}
    {% methodology_badge "similarity" %}

    {# Variable retrieval for custom rendering #}
    {% get_methodology "recurrence" as rec_notice %}
"""

from django import template
from django.utils.safestring import mark_safe
from django.utils.html import escape
from apps.incidents.services.methodology import get_methodology_notice, get_all_methodology_notices

register = template.Library()


@register.simple_tag
def get_methodology(key: str) -> dict:
    """Assigns the methodology notice dictionary to a template context variable."""
    return get_methodology_notice(key)


@register.simple_tag
def methodology_badge(key: str, extra_classes: str = "") -> str:
    """
    Renders an accessible inline badge displaying the methodology label
    with the canonical disclosure text in the tooltip (title attribute).
    """
    notice = get_methodology_notice(key)
    badge_label = escape(notice.get("badge_label", "Methodology"))
    summary = escape(notice.get("summary", ""))
    
    html = (
        f'<span class="methodology-badge inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs '
        f'font-medium bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 '
        f'border border-slate-200 dark:border-slate-700 cursor-help {escape(extra_classes)}" '
        f'title="{summary}" data-methodology-key="{escape(key)}" aria-label="{badge_label}: {summary}">'
        f'<svg class="w-3 h-3 text-slate-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">'
        f'<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />'
        f'</svg>'
        f'{badge_label}'
        f'</span>'
    )
    return mark_safe(html)


@register.simple_tag
def methodology_notice(key: str, compact: bool = False, extra_classes: str = "") -> str:
    """
    Renders a standard, accessible methodology disclosure banner / card.
    """
    notice = get_methodology_notice(key)
    title = escape(notice.get("title", "Analytical Methodology"))
    summary = escape(notice.get("summary", ""))
    badge_label = escape(notice.get("badge_label", "Notice"))
    provenance = escape(notice.get("provenance", ""))

    if compact:
        html = (
            f'<div class="methodology-notice-compact flex items-start gap-2 p-2.5 rounded-lg '
            f'bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 text-xs '
            f'text-slate-600 dark:text-slate-400 {escape(extra_classes)}" data-methodology-key="{escape(key)}">'
            f'<span class="inline-flex px-1.5 py-0.5 rounded text-[10px] font-semibold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-800 shrink-0">{badge_label}</span>'
            f'<div class="leading-relaxed"><strong class="text-slate-800 dark:text-slate-200 font-medium">{title}:</strong> {summary}</div>'
            f'</div>'
        )
    else:
        caveats = notice.get("caveats", [])
        caveats_html = ""
        if caveats:
            items = "".join(f'<li class="mt-1">{escape(c)}</li>' for c in caveats)
            caveats_html = f'<ul class="mt-1.5 list-disc list-inside text-xs text-slate-500 dark:text-slate-400 space-y-0.5">{items}</ul>'

        html = (
            f'<div class="methodology-notice p-4 rounded-xl bg-slate-50/80 dark:bg-slate-900/60 '
            f'border border-slate-200 dark:border-slate-800 {escape(extra_classes)}" data-methodology-key="{escape(key)}">'
            f'<div class="flex items-center justify-between gap-3 mb-1.5">'
            f'  <div class="flex items-center gap-2">'
            f'    <span class="inline-flex px-2 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-800">{badge_label}</span>'
            f'    <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-300">{title}</h4>'
            f'  </div>'
            f'  <span class="text-[11px] font-mono text-slate-400 dark:text-slate-500">{provenance}</span>'
            f'</div>'
            f'<p class="text-xs text-slate-600 dark:text-slate-300 font-medium leading-relaxed">{summary}</p>'
            f'{caveats_html}'
            f'</div>'
        )
    return mark_safe(html)
