import React from 'react';

export function SectionPicker({label,items,value,onChange,navigation=false,className=''}) {
 const ItemGroup=navigation?'nav':'div';
 return <ItemGroup className={`ws-section-picker ${className}`} aria-label={label} role={navigation?undefined:'group'}>
  {items.map(({id,label,icon:Icon})=><button key={id} type="button"
   aria-current={navigation&&value===id?'page':undefined}
   aria-pressed={navigation?undefined:value===id}
   onClick={()=>onChange(id)}>
   {Icon&&<Icon aria-hidden="true" size={16}/>}<span>{label}</span>
  </button>)}
 </ItemGroup>;
}

export function PageEmpty({icon:Icon,title,description,children,compact=false,busy=false}) {
 return <div className={`ws-page-empty${compact?' is-compact':''}`} aria-busy={busy||undefined}>
  {Icon&&<span className="ws-empty-symbol"><Icon aria-hidden="true" size={19}/></span>}
  <div className="ws-empty-content">
   <div role="status"><strong>{title}</strong>{description&&<p>{description}</p>}</div>
   {children&&<div className="ws-actions">{children}</div>}
  </div>
 </div>;
}
