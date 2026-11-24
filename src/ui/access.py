import hashlib
import hmac

import streamlit as st


def invitation_configured(cfg):
    return len(cfg.APP_ACCESS_TOKEN.get_secret_value().strip()) >= 24


def authorized(cfg):
    if not invitation_configured(cfg):
        return False
    token = cfg.APP_ACCESS_TOKEN.get_secret_value()
    return hmac.compare_digest(
        st.session_state.get("authorized_invitation", ""),
        hashlib.sha256(token.encode()).hexdigest(),
    )


def invitation_form(cfg):
    with st.form("invitation", clear_on_submit=True):
        token = st.text_input("Code d’invitation", type="password")
        if st.form_submit_button("Accéder à ORVANE"):
            expected = cfg.APP_ACCESS_TOKEN.get_secret_value()
            if invitation_configured(cfg) and hmac.compare_digest(
                token.encode(), expected.encode()
            ):
                st.session_state.authorized_invitation = hashlib.sha256(
                    expected.encode()
                ).hexdigest()
                st.rerun()
            st.error("Code d’invitation incorrect.")


def provider_button(label, key, cfg, help_text):
    available = bool(key.get_secret_value().strip()) and invitation_configured(cfg)
    if not available:
        st.button(label, disabled=True, help="Service indisponible pour cette session.")
        return False
    if authorized(cfg):
        return st.button(label, type="primary", help=help_text)
    with st.expander(f"{label} · Accès sur invitation"):
        invitation_form(cfg)
    return False
