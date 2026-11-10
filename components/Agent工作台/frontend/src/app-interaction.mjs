// UI continuity only; no business state or task execution.
export function navigateTrail(trail,next){
 if(trail.at(-1)===next)return trail;
 if(trail.at(-2)===next)return trail.slice(0,-1);
 return [...trail,next].slice(-30);
}
export function remoteSurface(current,previous){return current?.online?current:previous;}
export function correctTrail(trail,actual){
 const previous=trail.slice(0,-1);return previous.at(-1)===actual?previous:[...previous,actual];
}
