import React, { useState } from 'react';
import Tooltip from './Tooltip';
import { Info, Eye, EyeOff } from 'lucide-react';

interface InputFieldProps {
  label?: string;
  name: string;
  type?:
    | 'text'
    | 'email'
    | 'password'
    | 'search'
    | 'number'
    | 'tel'
    | 'date'
    | 'datetime-local'
    | 'time';
  placeholder?: string;
  value?: string | number;
  onBlur?: () => void;
  onChange: (name: string, value: string) => void;
  required?: boolean;
  error?: string;
  className?: string;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  size?: 'xs' | 'md' | 'lg';
  disabled?: boolean;
  min?: string | number;
  max?: string | number;
  step?: number;
  tooltip?: React.ReactNode;
  inputStyle?: string;
  allowDecimal?: boolean;
}

const TRIMMABLE_TYPES = ['text', 'email', 'search', 'tel', 'password'] as const;

const InputField: React.FC<InputFieldProps> = ({
  label,
  name,
  type = 'text',
  placeholder,
  value,
  onBlur,
  onChange,
  required = false,
  error,
  className = '',
  leftIcon,
  rightIcon,
  size = 'lg',
  disabled = false,
  min,
  max,
  step,
  tooltip,
  inputStyle = '',
  allowDecimal = true,
}) => {
  const [showPassword, setShowPassword] = useState(false);
  const sizeClasses = {
    xs: 'px-3 py-1.5 text-xs',
    md: 'px-3.5 py-2 text-sm',
    lg: 'px-4 py-2.5 text-sm',
  };
  const handleTogglePassword = () => {
    if (disabled) return;
    setShowPassword((prev) => !prev);
  };

  const handleBlur = (e: React.FocusEvent<HTMLInputElement>) => {
    if (
      !disabled &&
      TRIMMABLE_TYPES.includes(type as (typeof TRIMMABLE_TYPES)[number])
    ) {
      const trimmed = e.target.value.trim();
      if (trimmed !== e.target.value) {
        onChange(name, trimmed);
      }
    }
    onBlur?.();
  };

  const inputType =
    type === 'password' ? (showPassword ? 'text' : 'password') : type;
  const handleWheel = (e: React.WheelEvent<HTMLInputElement>) => {
    if (type === 'number' && !disabled) {
      (e.target as HTMLInputElement).blur();
    }
  };
  return (
    <div className={`${className}`}>
      {(label || tooltip) && (
        <div className="flex items-center gap-1 mb-1.5">
          {label && (
            <label className="block text-sm font-medium text-gray-700 font-poppins">
              {label}
              {required && <span className="text-danger ml-[2px]">*</span>}
            </label>
          )}
          {tooltip && (
            <Tooltip content={tooltip}>
              <Info className="w-4 h-4" />
            </Tooltip>
          )}
        </div>
      )}

      <div className="relative">
        {leftIcon && (
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <div
              className={`h-4 w-4 ${disabled ? 'text-gray-300' : 'text-gray-400'}`}
            >
              {leftIcon}
            </div>
          </div>
        )}
        <input
          type={inputType}
          name={name}
          placeholder={placeholder || 'Enter value'}
          value={value}
          disabled={disabled}
          min={min}
          max={max}
          step={step}
          onBlur={handleBlur}
          onWheel={handleWheel}
          onChange={(e) => onChange(name, e.target.value)}
          onKeyDown={(e) => {
            if (type === 'number' && !allowDecimal) {
              if (e.key === '.' || e.key === 'e' || e.key === 'E') {
                e.preventDefault();
              }
            }
          }}
          aria-invalid={error ? 'true' : 'false'}
          className={`w-full border rounded-lg placeholder-gray-400 
            focus:outline-none focus:ring-2 transition-all duration-200 shadow-sm font-poppins
            ${sizeClasses[size]}
            ${leftIcon ? 'pl-10' : ''} ${rightIcon ? 'pr-10' : ''}
            ${
              disabled
                ? 'bg-gray-100 text-gray-600 cursor-not-allowed'
                : 'bg-white text-gray-700'
            }
            ${
              error
                ? 'border-danger focus:ring-danger focus:border-danger'
                : 'border-[#a0a7c0] focus:ring-[#7b61ff] focus:border-transparent'
            }
             ${inputStyle}`}
        />
        {type === 'password' && (
          <div className="absolute inset-y-0 right-0 pr-3 flex items-center z-10">
            <div
              className={`${disabled ? 'text-gray-300' : 'text-gray-400'} h-4 w-4`}
            >
              <button
                type="button"
                onClick={handleTogglePassword}
                className="text-gray-400 hover:text-gray-600 focus:outline-none"
                tabIndex={-1}
              >
                {showPassword ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>
        )}

        {rightIcon && (
          <div className="absolute inset-y-0 right-0 pr-3 flex items-center z-10">
            <div
              className={`${disabled ? 'text-gray-300' : 'text-gray-400'} h-4 w-4`}
            >
              {rightIcon}
            </div>
          </div>
        )}
      </div>

      {error && !disabled && (
        <p className="text-xs text-danger !mt-1 !ml-1">{error}</p>
      )}
    </div>
  );
};

export default InputField;
