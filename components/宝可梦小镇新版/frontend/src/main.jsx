import {createRoot} from 'react-dom/client';
import {RoomTown} from './RoomTown.jsx';
import {TownPortal} from './TownPortal.jsx';
import {ErrorBoundary} from './components/ErrorBoundary.jsx';
import './styles.css';import './room-town.css';import './cottage-ui.css';
document.body.classList.add('room-embedded');
const alarm=new URLSearchParams(location.search).get('room')==='alarm';
createRoot(document.getElementById('root')).render(<ErrorBoundary>{alarm?<RoomTown/>:<TownPortal/>}</ErrorBoundary>);
