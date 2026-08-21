"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * A complete ARIA tabs implementation.
 *
 * The previous version declared `role="tablist"`/`role="tab"` without
 * `aria-controls`, matching ids, or arrow-key navigation. An incomplete ARIA
 * pattern is worse for a screen-reader user than plain buttons: it promises
 * behaviour that is not there. This wires the ids and implements the roving
 * tabindex the pattern requires.
 */

interface TabsContextValue {
  value: string;
  setValue: (value: string) => void;
  baseId: string;
  register: (value: string) => void;
  unregister: (value: string) => void;
  order: React.RefObject<string[]>;
}
const TabsContext = React.createContext<TabsContextValue | null>(null);

function useTabs(component: string): TabsContextValue {
  const context = React.useContext(TabsContext);
  if (!context) {
    throw new Error(`<${component}> must be rendered inside <Tabs>`);
  }
  return context;
}

const tabId = (baseId: string, value: string) => `${baseId}-tab-${value}`;
const panelId = (baseId: string, value: string) => `${baseId}-panel-${value}`;

interface TabsProps extends React.HTMLAttributes<HTMLDivElement> {
  value: string;
  onValueChange?: (value: string) => void;
}

function Tabs({ value, onValueChange, className, children, ...props }: TabsProps) {
  const baseId = React.useId();
  // Registration order is DOM order, which is what arrow keys must follow.
  const order = React.useRef<string[]>([]);

  const register = React.useCallback((tab: string) => {
    if (!order.current.includes(tab)) order.current.push(tab);
  }, []);
  const unregister = React.useCallback((tab: string) => {
    order.current = order.current.filter((t) => t !== tab);
  }, []);

  const context = React.useMemo<TabsContextValue>(
    () => ({
      value,
      setValue: onValueChange ?? (() => {}),
      baseId,
      register,
      unregister,
      order,
    }),
    [value, onValueChange, baseId, register, unregister],
  );

  return (
    <TabsContext.Provider value={context}>
      <div className={cn("flex flex-col", className)} {...props}>
        {children}
      </div>
    </TabsContext.Provider>
  );
}

function TabsList({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      role="tablist"
      className={cn(
        "inline-flex h-9 items-center justify-center rounded-lg bg-muted p-1 text-muted-foreground",
        className
      )}
      {...props}
    />
  );
}

interface TabsTriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  value: string;
}

function TabsTrigger({ className, value, children, onKeyDown, ...props }: TabsTriggerProps) {
  const context = useTabs("TabsTrigger");
  const active = context.value === value;

  React.useEffect(() => {
    context.register(value);
    return () => context.unregister(value);
  }, [context, value]);

  const move = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    onKeyDown?.(event);
    if (event.defaultPrevented) return;

    const tabs = context.order.current;
    const index = tabs.indexOf(value);
    if (index === -1) return;

    let next: number | null = null;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    if (next === null) return;

    event.preventDefault();
    const target = tabs[next];
    context.setValue(target);
    document.getElementById(tabId(context.baseId, target))?.focus();
  };

  return (
    <button
      type="button"
      role="tab"
      id={tabId(context.baseId, value)}
      aria-selected={active}
      aria-controls={panelId(context.baseId, value)}
      // Roving tabindex: only the selected tab is in the tab order; the rest
      // are reached with arrow keys, per the ARIA tabs pattern.
      tabIndex={active ? 0 : -1}
      onClick={() => context.setValue(value)}
      onKeyDown={move}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md px-3 py-1 text-sm font-medium transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
        active ? "bg-card text-foreground shadow-sm" : "hover:text-foreground",
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}

interface TabsContentProps extends React.HTMLAttributes<HTMLDivElement> {
  value: string;
}

function TabsContent({ className, value, children, ...props }: TabsContentProps) {
  const context = useTabs("TabsContent");
  if (context.value !== value) return null;
  return (
    <div
      role="tabpanel"
      id={panelId(context.baseId, value)}
      aria-labelledby={tabId(context.baseId, value)}
      tabIndex={0}
      className={cn("mt-2 flex-1", className)}
      {...props}
    >
      {children}
    </div>
  );
}

export { Tabs, TabsList, TabsTrigger, TabsContent };
