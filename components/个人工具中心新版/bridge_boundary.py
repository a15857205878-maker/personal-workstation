"""Restrict pywebview's native dispatcher before importing its GUI platform.

Generated JS API visibility alone is not an authorization boundary in 6.2.1.
This app exposes one registered function; no object traversal or DOM/state APIs.
"""
import logging,math

def install_boundary():
    import webview.util
    original=webview.util.js_bridge_call
    if getattr(original,'_tool_center_boundary',False):return
    def dispatch(window,name,params,value_id):
        if (name=='pywebviewMoveWindow' and getattr(window,'_workstation_native_drag',False) is True
                and isinstance(params,list) and len(params)==2
                and all(type(value) in (int,float) and abs(value)<=100000 and math.isfinite(value) for value in params)):
            return original(window,name,params,value_id)
        if name=='call' and window._js_api is None and callable(window._functions.get('call')):
            if isinstance(params,list) and 1<=len(params)<=2:
                return original(window,name,params,value_id)
        elif name=='pywebviewAsyncCallback' and value_id in window._callbacks:
            return original(window,name,params,value_id)
        logging.getLogger('toolcenter').warning('Rejected unregistered native bridge operation')
    dispatch._tool_center_boundary=True
    webview.util.js_bridge_call=dispatch
