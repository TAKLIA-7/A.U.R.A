// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from './App';

const scenarios=[
 {scenario_id:'S001',name:'Sensitive export',category:'exfiltration',description:'Export protected fields',is_attack:true,severity:'high',expected_security_outcome:'BLOCK'},
 {scenario_id:'S002',name:'Allowed lookup',category:'legitimate',description:'Read permitted record',is_attack:false,severity:'low',expected_security_outcome:'ALLOW'},
];
const trials=[
 {id:'t1',experiment_id:'e1',scenario_id:'S001',mode:'baseline',repetition:1,completed:true,harmful_effect:true,task_success:false,latency_ms:100,tokens:null,created_at:'2026-01-01'},
 {id:'t2',experiment_id:'e1',scenario_id:'S001',mode:'aura',repetition:1,completed:true,harmful_effect:false,task_success:true,latency_ms:125,tokens:null,created_at:'2026-01-01'},
 {id:'t3',experiment_id:'e1',scenario_id:'S002',mode:'baseline',repetition:1,completed:true,harmful_effect:false,task_success:true,latency_ms:90,tokens:null,created_at:'2026-01-01'},
 {id:'t4',experiment_id:'e1',scenario_id:'S002',mode:'aura',repetition:1,completed:true,harmful_effect:false,task_success:true,latency_ms:115,tokens:null,created_at:'2026-01-01'},
];
function setupFetch(){const data=[[],scenarios,trials,[],[]];vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL)=>{const path=String(input);const index=path.includes('/experiments')?0:path.includes('/scenarios')?1:path.includes('/metrics/trials')?2:path.includes('/tool-calls')?3:4;return {ok:true,json:async()=>data[index]} as Response}))}
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
describe('AURA dashboard',()=>{
 it('renders persisted comparison rates and unavailable usage clearly',async()=>{setupFetch();render(<App/>);await waitFor(()=>expect(document.querySelector('.filter-row')?.textContent).toContain('4 matching records'));expect((await screen.findAllByText('100.0%')).length).toBe(2);expect(screen.getByText('Unknown ≠ zero')).toBeTruthy()});
 it('global scenario filter updates the displayed trial population',async()=>{setupFetch();render(<App/>);await waitFor(()=>expect(document.querySelector('.filter-row')?.textContent).toContain('4 matching records'));fireEvent.change(screen.getByRole('combobox',{name:'Scenario type'}),{target:{value:'exfiltration'}});await waitFor(()=>expect(document.querySelector('.filter-row')?.textContent).toContain('2 matching records'));expect(await screen.findByText(/1 prevented \/ 1 completed attack trials/)).toBeTruthy()});
 it('shows a recoverable API error when backend is unavailable',async()=>{vi.stubGlobal('fetch',vi.fn(async()=>({ok:false,json:async()=>[]})));render(<App/>);expect(await screen.findByText(/Could not load dashboard data/)).toBeTruthy();expect(screen.getByRole('button',{name:'Retry'})).toBeTruthy()});
});
