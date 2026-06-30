export function interpolateTemplate(template: string, ctx: Record<string, string>): string {
  return template.replace(/{{([\w.-]+)}}/g, (_match, key: string) => ctx[key] ?? `{{${key}}}`);
}
