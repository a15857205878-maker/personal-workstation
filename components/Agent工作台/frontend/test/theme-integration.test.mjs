import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const here=path.dirname(fileURLToPath(import.meta.url));
const root=process.env.WORKSTATION_FRONTEND_ROOT||path.resolve(here,'..');
const read=name=>readFileSync(path.join(root,name),'utf8');
const main=read('src/main.jsx');
const layout=read('src/workstation-layout.jsx');
const titlebar=read('src/desktop-titlebar.jsx');
const unified=read('src/unified-theme.css');
const appLayout=read('src/app-layout.css');
const theme=read('src/theme.css');
const toolsEntry=read('src/original-tools-entry.jsx');
const build=read('build.mjs');

test('single titlebar is mounted once and the old sidebar brand is gone',()=>{
 assert.match(layout,/import DesktopTitlebar from '\.\/desktop-titlebar\.jsx';/);
 assert.equal((layout.match(/<DesktopTitlebar\/>/g)||[]).length,1);
 assert.doesNotMatch(layout,/className="app-brand"/);
 assert.doesNotMatch(layout,/<ThemePicker/);
 assert.doesNotMatch(layout,/个人工作站/);
 assert.equal((titlebar.match(/个人工作站/g)||[]).length,1);
 assert.match(titlebar,/className="desktop-drag-region pywebview-drag-region"/);
 const start=titlebar.indexOf('desktop-drag-region');
 const end=titlebar.indexOf('</div>',start);
 const drag=titlebar.slice(start,end);
 assert.match(drag,/个人工作站/);
 assert.doesNotMatch(drag,/<button|<select|ThemePicker|theme-scheme/);
 assert.match(titlebar,/onDoubleClick=\{toggle\}/);
});

test('window controls are ordered, labelled and sized in CSS',()=>{
 const buttons=titlebar.slice(titlebar.indexOf('desktop-window-buttons'));
 const minimize=buttons.indexOf("run('minimize')");
 const maximize=buttons.indexOf('onClick={toggle}');
 const close=buttons.indexOf("run('close')");
 assert.ok(minimize>0&&maximize>minimize&&close>maximize);
 assert.match(titlebar,/aria-label=\"最小化窗口\"/);
 assert.match(titlebar,/aria-label=\{maximizeLabel\}/);
 assert.match(titlebar,/aria-label=\"关闭窗口\"/);
 assert.match(titlebar,/run\('toggle_maximize'\)/);
 assert.match(titlebar,/window-workstation-state/);
 assert.match(titlebar,/role="alert"/);
 assert.match(unified,/\.desktop-titlebar\{[^}]*height:40px/);
 assert.match(unified,/\.desktop-window-button\{[^}]*width:46px[^}]*height:40px/);
 assert.match(unified,/\.desktop-window-button\.is-close:hover[^}]*background:#c94848/);
 assert.match(unified,/\.desktop-titlebar-tools\{[^}]*flex:0 0 auto/);
});

test('two schemes keep the agreed geometry and palette',()=>{
 for(const value of ['#151c27','#101721','#1e2938','#35445a','#e6edf6','#edf3f9','#e3ebf5','#fbfdff','#d4dfec','#24354c'])assert.ok(unified.includes(value),value);
 for(const value of ['#5e9df6','#52b99e','#ad91e2','#d8ad59','#d98982'])assert.ok(unified.includes(value),value);
 assert.match(unified,/\.app-shell\{[^}]*grid-template-rows:40px minmax\(0,1fr\)/);
 assert.match(unified,/\.app-main\{[^}]*grid-template-rows:48px minmax\(0,1fr\)/);
 assert.match(appLayout,/grid-template-rows:48px minmax\(0,1fr\)/);
 assert.match(appLayout,/calc\(100vh - 88px\)/);
 assert.match(unified,/\.app-shell \.ws-card\{[^}]*border-radius:8px/);
 assert.doesNotMatch(theme,/data-palette=(mint|blue|lavender|apricot|coastal)/);
 assert.doesNotMatch(read('src/theme-picker.jsx'),/aria-label="界面配色"/);
});

test('themes are persisted through the API and applied through DOM attributes',()=>{
 assert.match(main,/import '\.\/app-layout\.css';\r?\nimport '\.\/unified-theme\.css';/);
 assert.match(main,/hidden=\{mode!==/);
 assert.doesNotMatch(main,/key=\{mode\}/);
 assert.doesNotMatch(main,/data-theme=/);
 assert.match(toolsEntry,/data-color-scheme','color-scheme'/);
 assert.doesNotMatch(toolsEntry,/attributeFilter:\['data-theme','style'\]/);
 assert.match(toolsEntry,/--surface','--app-surface'/);
 assert.match(build,/syncTheme/);
 assert.match(build,/parent\.document\.documentElement/);
 assert.match(build,/attributeFilter:\['data-color-scheme','color-scheme','data-palette'\]/);
 assert.match(build,/workstation_town_call/);
});

test('the injected town bridge compiles and forwards the shell tokens',()=>{
 const match=build.match(/const shim=`([\s\S]*?)`;/);
 assert.ok(match,'town shim literal missing');
 assert.doesNotThrow(()=>new Function(match[1]));
 assert.match(match[1],/--paper/);
 assert.match(match[1],/--app-surface/);
 assert.match(match[1],/root\.dataset\.theme=scheme/);
 assert.match(match[1],/workstation_town_call/);
});

test('motion is scoped, short and reduced-motion safe; iframes are never filtered',()=>{
 assert.match(unified,/@keyframes app-pane-enter\{from\{opacity:0;transform:translateY\(4px\)\}/);
 assert.match(unified,/app-pane-enter \.16s/);
 assert.match(unified,/grid-template-columns \.18s/);
 assert.match(unified,/background-color \.18s/);
 assert.match(unified,/@media\(prefers-reduced-motion:reduce\)/);
 assert.doesNotMatch(unified,/transition:all/);
 assert.doesNotMatch(unified,/invert\(/);
 assert.doesNotMatch(unified,/filter:/);
 assert.doesNotMatch(appLayout,/transition:all/);
});
