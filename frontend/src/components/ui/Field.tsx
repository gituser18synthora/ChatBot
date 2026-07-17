import {
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
  type InputHTMLAttributes,
  Children,
  isValidElement,
  useState,
  useRef,
  useEffect,
  useCallback,
  useMemo,
} from "react";
import { createPortal } from "react-dom";
import { ChevronDown, Search } from "lucide-react";
import { cn } from "@/lib/utils";

export function Field({
  label,
  error,
  hint,
  required,
  children,
}: {
  label?: string;
  error?: string;
  hint?: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <div>
      {label && (
        <label className="label">
          {label}
          {required && <span className="ml-0.5 text-rose-500">*</span>}
        </label>
      )}
      {children}
      {hint && !error && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
      {error && <p className="mt-1 text-xs text-rose-600">{error}</p>}
    </div>
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  const { invalid, className, ...rest } = props;
  return <input className={cn("input", invalid && "border-rose-400 focus:ring-rose-200", className)} {...rest} />;
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const { className, ...rest } = props;
  return <textarea className={cn("input resize-y", className)} {...rest} />;
}

interface ParsedOption {
  value: string;
  label: string;
  disabled?: boolean;
}
interface SelectExtraProps {
  searchable?: boolean;
  searchPlaceholder?: string;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement> & SelectExtraProps) {
  const {
    className,
    children,
    value,
    onChange,
    disabled,
    name,
    id,
    searchable = true,
    searchPlaceholder = "Search...",
    ...rest
  } = props;

  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [position, setPosition] = useState({ top: 0, left: 0, width: 0 });
  const [dropdownHeight, setDropdownHeight] = useState(0);

  const buttonRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const options = useMemo<ParsedOption[]>(() => {
    const result: ParsedOption[] = [];
    Children.forEach(children, (child) => {
      if (!isValidElement(child)) return;

      if (child.type === "option") {
        const childProps = child.props as { value?: string; children?: ReactNode; disabled?: boolean };
        result.push({
          value: String(childProps.value ?? ""),
          label: typeof childProps.children === "string" ? childProps.children : String(childProps.children ?? ""),
          disabled: childProps.disabled,
        });
        return;
      }
      if (child.type === "optgroup") {
        const groupProps = child.props as { children?: ReactNode };
        Children.forEach(groupProps.children, (grandchild) => {
          if (!isValidElement(grandchild) || grandchild.type !== "option") return;
          const childProps = grandchild.props as { value?: string; children?: ReactNode; disabled?: boolean };
          result.push({
            value: String(childProps.value ?? ""),
            label: typeof childProps.children === "string" ? childProps.children : String(childProps.children ?? ""),
            disabled: childProps.disabled,
          });
        });
      }
    });
    return result;
  }, [children]);

  const selected = options.find((o) => o.value === value);
  const filtered = searchable
    ? options.filter((o) => o.label.toLowerCase().includes(search.toLowerCase()))
    : options;

  useEffect(() => {
    if (isOpen && dropdownRef.current) {
      setDropdownHeight(dropdownRef.current.offsetHeight);
    }
  }, [isOpen, search]);

  const updatePosition = useCallback(() => {
    if (!buttonRef.current) return;
    const rect = buttonRef.current.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const spaceAbove = rect.top;
    const top =
      spaceBelow > 220 || spaceBelow > spaceAbove
        ? rect.bottom + window.scrollY + 4
        : rect.top + window.scrollY - dropdownHeight - 4;
    setPosition({
      top,
      left: rect.left + window.scrollX,
      width: rect.width,
    });
  }, [dropdownHeight]);

  useEffect(() => {
    if (!isOpen) return;
    updatePosition();
    const update = () => updatePosition();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [isOpen, updatePosition]);

  useEffect(() => {
    if (!isOpen) return;
    const click = (e: MouseEvent) => {
      if (
        !dropdownRef.current?.contains(e.target as Node) &&
        !buttonRef.current?.contains(e.target as Node)
      ) {
        setIsOpen(false);
        setSearch("");
      }
    };
    document.addEventListener("mousedown", click);
    return () => document.removeEventListener("mousedown", click);
  }, [isOpen]);

  const emitChange = (nextValue: string) => {
    if (!onChange) return;
    const syntheticEvent = {
      target: { value: nextValue, name },
      currentTarget: { value: nextValue, name },
    } as unknown as React.ChangeEvent<HTMLSelectElement>;
    onChange(syntheticEvent);
  };

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        id={id}
        disabled={disabled}
        onClick={() => !disabled && setIsOpen((v) => !v)}
        className={cn(
          "input flex items-center justify-between",
          disabled && "opacity-60 cursor-not-allowed",
          className
        )}
        {...(rest as Record<string, unknown>)}
      >
        <span className={cn("truncate", selected ? "text-slate-900" : "text-slate-400")}>
          {selected?.label ?? "Select an option"}
        </span>
        <ChevronDown className={cn("h-4 w-4 flex-none transition-transform", isOpen && "rotate-180")} />
      </button>

      {isOpen &&
        createPortal(
          <div
            ref={dropdownRef}
            className="fixed z-50 rounded-xl border border-slate-200 bg-white shadow-xl overflow-hidden"
            style={{
              top: position.top,
              left: position.left,
              width: position.width,
            }}
          >
            {searchable && (
              <div className="border-b p-2">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <input
                    autoFocus
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder={searchPlaceholder}
                    className="w-full rounded-md border border-slate-300 py-2 pl-9 pr-3 text-sm outline-none focus:ring-2 focus:ring-slate-300"
                  />
                </div>
              </div>
            )}
            <div className="max-h-60 overflow-y-auto p-2 no-scrollbar">
              {filtered.length ? (
                filtered.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    disabled={option.disabled}
                    onClick={() => {
                      if (option.disabled) return;
                      emitChange(option.value);
                      setIsOpen(false);
                      setSearch("");
                    }}
                    className={cn(
                      "w-full rounded-md px-3 py-2 text-left text-sm transition-colors",
                      option.disabled
                        ? "cursor-not-allowed text-slate-400"
                        : "hover:bg-slate-100",
                      value === option.value && "bg-primary text-white hover:!bg-primary"
                    )}
                  >
                    {option.label}
                  </button>
                ))
              ) : (
                <div className="px-3 py-2 text-sm text-slate-500">No options found</div>
              )}
            </div>
          </div>,
          document.body
        )}
    </>
  );
}