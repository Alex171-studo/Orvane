from html import escape

import streamlit as st


def brand():
    st.sidebar.html("""
    <div class="orvane-brand">
      <div class="orvane-mark" aria-hidden="true"><i></i><i></i><i></i></div>
      <div><strong>ORVANE</strong><small>Du terrain à la décision.</small></div>
    </div>
    <style>
    .orvane-brand{display:flex;gap:13px;align-items:center;margin:0 0 1.35rem;color:#172554}
    .orvane-brand strong{font:750 1.5rem/1.1 system-ui;letter-spacing:.12em}
    .orvane-brand small{display:block;font:400 .83rem/1.8 system-ui;color:#475569}
    .orvane-mark{display:flex;align-items:flex-end;gap:3px;background:#172554;padding:10px;
      height:42px;width:42px;box-sizing:border-box;border-radius:7px}
    .orvane-mark i{display:block;background:#fff;width:5px;height:11px}
    .orvane-mark i:nth-child(2){height:20px;background:#93c5fd}
    .orvane-mark i:nth-child(3){height:15px}
    </style>
    """)


def metric_grid(metrics):
    cards = "".join(
        f"<div><dt>{escape(label)}</dt><dd>{escape(str(value))}</dd></div>"
        for label, value in metrics
    )
    st.html(
        """
    <style>
    .orvane-kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.7rem;margin:.25rem 0}
    .orvane-kpis div{padding:1rem;background:#fff;border:1px solid #e2e8f0;border-radius:.5rem}
    .orvane-kpis dt{color:#475569;font:500 .85rem/1.3 system-ui}
    .orvane-kpis dd{margin:.4rem 0 0;color:#172554;font:600 1.8rem/1.1 system-ui;font-variant-numeric:tabular-nums}
    @media(max-width:800px){.orvane-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
    .orvane-kpis div:last-child{grid-column:1/-1;display:flex;align-items:center;justify-content:space-between}
    .orvane-kpis div:last-child dd{margin:0}}
    </style><dl class="orvane-kpis">"""
        + cards
        + "</dl>"
    )
