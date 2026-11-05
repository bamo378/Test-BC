import {localRequest} from './pages-data.js';
export const staticMode=typeof document!=='undefined'&&document.documentElement.dataset.hosting==='github-pages';
export const apiFetch=(path,options)=>staticMode?localRequest(path,options):fetch(path,options);
