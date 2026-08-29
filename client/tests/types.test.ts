/**
 * §12.5: the types.ts protocol-version guard. The client must refuse to run —
 * not warn, not degrade — when the server speaks a different protocol version.
 */
import { describe, expect, it } from 'vitest';

import { PROTOCOL_VERSION, protocolMismatch } from '../src/types';

describe('protocolMismatch', () => {
  it('accepts the matching version', () => {
    expect(protocolMismatch(PROTOCOL_VERSION)).toBeNull();
  });

  it('refuses any other version, naming both sides', () => {
    const refusal = protocolMismatch(PROTOCOL_VERSION + 1);
    console.log(`  refusal text: ${refusal}`);
    expect(refusal).not.toBeNull();
    expect(refusal).toContain(`v${PROTOCOL_VERSION + 1}`);
    expect(refusal).toContain(`v${PROTOCOL_VERSION}`);
    expect(refusal?.toLowerCase()).toContain('refusing to run');
  });

  it('refuses an older server too — skew is skew in both directions', () => {
    expect(protocolMismatch(0)).not.toBeNull();
  });
});
