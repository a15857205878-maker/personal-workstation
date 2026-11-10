import { useCallback, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { useToolCenter } from '../../../个人工具中心新版/frontend/src/hooks/useToolCenter.js';
import { GamesPage } from '../../../个人工具中心新版/frontend/src/pages/Games.jsx';
import { PackPage } from '../../../个人工具中心新版/frontend/src/pages/Pack.jsx';
import { WheelPage } from '../../../个人工具中心新版/frontend/src/pages/Wheel.jsx';
import { ConnectionScreen } from '../../../个人工具中心新版/frontend/src/components/ConnectionScreen.jsx';
import { ErrorBoundary } from '../../../个人工具中心新版/frontend/src/components/ErrorBoundary.jsx';
import { ToastProvider, ToastViewport, useToastStore } from '../../../个人工具中心新版/frontend/src/components/Toasts.jsx';
import { InlineAlert } from '../../../个人工具中心新版/frontend/src/components/ui.jsx';
import '../../../个人工具中心新版/frontend/src/styles.css';
import '../../../个人工具中心新版/frontend/src/finish.css';
import './original-tools-frame.css';

const PAGES = new Set(['pack', 'games', 'wheel']);
function hashPage() {
  const page = window.location.hash.slice(1);
  return PAGES.has(page) ? page : 'pack';
}

// Keep the original pages and dialogs mounted so drafts and wheel animation survive navigation.
function OriginalTools() {
  useEffect(() => {
    const host=parent.document.documentElement;
    const sync=()=>{
      const style=parent.getComputedStyle(host);
      const scheme=host.dataset.colorScheme==='dark'?'dark':'light';
      document.documentElement.dataset.theme=scheme;
      document.documentElement.style.colorScheme=scheme;
      for(const [target,source] of [
        ['--bg','--app-bg'],['--bg-deep','--app-surface-2'],['--surface','--app-surface'],['--surface-soft','--app-surface-2'],['--surface-muted','--app-surface-3'],['--surface-strong','--app-border'],['--border','--app-border'],['--border-strong','--app-border-strong'],['--text','--app-text'],['--text-secondary','--app-text-2'],['--text-muted','--app-muted'],['--primary','--app-primary'],['--primary-strong','--app-primary-strong'],['--primary-soft','--app-primary-soft'],['--primary-contrast','--app-on-primary'],['--focus','--app-primary'],['--mint','--app-jade'],['--mint-strong','--app-jade-ink'],['--mint-soft','--app-jade-soft'],['--success','--app-jade-ink'],['--success-soft','--app-jade-soft'],['--danger','--app-danger'],['--danger-strong','--app-danger'],['--danger-soft','--app-coral-soft'],['--warning','--app-amber-ink'],['--warning-soft','--app-amber-soft'],['--info','--app-primary-ink'],['--info-soft','--app-primary-soft']
      ]){
        const value=style.getPropertyValue(source).trim();
        if(value)document.documentElement.style.setProperty(target,value);else document.documentElement.style.removeProperty(target);
      }
    };
    sync();const observer=new MutationObserver(sync);observer.observe(host,{attributes:true,attributeFilter:['data-color-scheme','color-scheme']});return()=>observer.disconnect();
  },[]);
  const center = useToolCenter();
  const toastStore = useToastStore();
  const [navigation, setNavigation] = useState(() => {
    const page = hashPage();
    return { page, visited: [page] };
  });
  const [retryBusy, setRetryBusy] = useState(false);
  const currentPage = useRef(navigation.page);
  const afterLaunchTimer = useRef(null);
  useEffect(() => {
    const navigate = () => {
      const page = hashPage();
      if (page !== currentPage.current && document.querySelector('[role="dialog"][aria-modal="true"]')) {
        // Original dialogs portal to body. Preserve their edits and explicit save/cancel flow.
        window.history.replaceState(null, '', `#${currentPage.current}`);
        toastStore.notify({ tone: 'info', title: '请先保存或关闭当前对话框', message: '当前表单已保留，关闭对话框后即可切换分区。' });
        parent.postMessage({ type: 'workstation-tools-navigation-blocked', page: currentPage.current }, window.location.origin);
        return;
      }
      currentPage.current = page;
      setNavigation(current => ({ page, visited: current.visited.includes(page) ? current.visited : [...current.visited, page] }));
    };
    window.addEventListener('hashchange', navigate);
    return () => window.removeEventListener('hashchange', navigate);
  }, [toastStore.notify]);
  useEffect(() => () => window.clearTimeout(afterLaunchTimer.current), []);

  const handleAfterLaunch = useCallback(() => {
    window.clearTimeout(afterLaunchTimer.current);
    afterLaunchTimer.current = window.setTimeout(async () => {
      const result = await center.refresh();
      if (!result.ok) toastStore.notify({ tone: 'info', title: '最近记录尚未同步', message: '启动请求已完成，但刷新最近使用记录失败；可稍后手动刷新。' });
    }, 600);
  }, [center.refresh, toastStore.notify]);
  const handleRetry = useCallback(async () => {
    setRetryBusy(true);
    try { await center.retry(); } finally { setRetryBusy(false); }
  }, [center.retry]);

  return <ToastProvider value={toastStore}>
    {!center.data ? <ConnectionScreen status={center.connection} error={center.connectionError} onRetry={handleRetry} busy={retryBusy} /> : <>
      {center.refreshError ? <div className="original-tools-banner"><InlineAlert tone="warning" title="刷新数据失败，正在显示上次载入的内容" onDismiss={center.clearRefreshError}>{center.refreshError}</InlineAlert></div> : null}
      <main className="page-scroll" id="main-content" tabIndex={-1}>
        {navigation.visited.map(page => <div key={page} hidden={navigation.page !== page} className="original-tools-page">
          {page === 'games' ? <GamesPage data={center.data} call={center.call} updateGames={center.updateGames} focusGameId={null} onFocusConsumed={() => {}} onAfterLaunch={handleAfterLaunch} /> : null}
          {page === 'pack' ? <PackPage data={center.data} jobs={center.jobs} jobPollError={center.jobPollError} call={center.call} packDraft={center.packDraft} setPackDraft={center.setPackDraft} updateMaterials={center.updateMaterials} lastPackJobId={center.lastPackJobId} addOrUpdateJob={center.addOrUpdateJob} focusMaterialId={null} onFocusConsumed={() => {}} /> : null}
          {page === 'wheel' ? <WheelPage data={center.data} call={center.call} updateWheel={center.updateWheel} focusWheelId={null} onFocusConsumed={() => {}} /> : null}
        </div>)}
      </main>
    </>}
    <ToastViewport toasts={toastStore.toasts} onDismiss={toastStore.dismiss} />
  </ToastProvider>;
}

createRoot(document.getElementById('root')).render(<ErrorBoundary><OriginalTools /></ErrorBoundary>);
