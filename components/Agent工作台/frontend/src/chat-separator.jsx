import React,{useRef} from 'react';
export default function ChatSeparator({axis,value,min,max,onChange,onReset,className,label}){
 const drag=useRef(null),vertical=axis==='width';
 const coordinate=e=>vertical?e.clientX:e.clientY;
 const stop=e=>{drag.current=null;if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);};
 return <div className={'chat-separator '+className} role="separator" tabIndex={0} aria-label={label} aria-orientation={vertical?'vertical':'horizontal'} aria-valuemin={min} aria-valuemax={max} aria-valuenow={value} title="拖动调整；方向键微调；双击或 Home 恢复" onPointerDown={e=>{if(e.button!==0)return;drag.current={position:coordinate(e),value};e.currentTarget.setPointerCapture(e.pointerId);e.preventDefault();}} onPointerMove={e=>{if(drag.current)onChange(drag.current.value+(coordinate(e)-drag.current.position)*(vertical?1:-1));}} onPointerUp={stop} onPointerCancel={stop} onLostPointerCapture={()=>{drag.current=null;}} onDoubleClick={onReset} onKeyDown={e=>{const keys=vertical?{ArrowLeft:-16,ArrowRight:16}:{ArrowUp:16,ArrowDown:-16};if(e.key in keys){e.preventDefault();onChange(value+keys[e.key]);}else if(e.key==='Home'){e.preventDefault();onReset();}}}><span aria-hidden="true"/></div>;
}
