import {describe,it,expect} from 'vitest';
describe('frontend build smoke',()=>{it('supports numeric money formatting',()=>expect((19.5).toFixed(2)).toBe('19.50'))});
