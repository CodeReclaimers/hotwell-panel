/** Runes mode is forced (PLAN-panel.md §1) so Svelte-4 legacy syntax
 * (`export let`, `$:`, stores-as-props) fails loudly instead of compiling. */
export default {
  compilerOptions: { runes: true },
};
