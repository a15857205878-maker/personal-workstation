export function taskTone(state){
 switch(state){
  case 'starting':
  case 'running':
  case 'stopping': return 'working';
  case 'prepared': return 'attention';
  case 'completed': return 'ready';
  case 'failed':
  case 'interrupted': return 'error';
  default: return 'neutral';
 }
}
