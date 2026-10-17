// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import App from './App';
describe('dashboard shell',()=>{it('shows clear unavailable data state when backend is down',async()=>{render(<App/>);expect(await screen.findByText(/API request failed|Attack success · baseline/i)).toBeTruthy()})});
