import streamlit as st


def brand():
    st.html("""
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
