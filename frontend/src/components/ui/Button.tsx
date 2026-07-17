import React from 'react';
import clsx from 'clsx';

// Simple local Loader to avoid external dependency import error
type LoaderProps = {
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
  color?: string;
  className?: string;
  type?: 'spinner' | string;
};

const Loader: React.FC<LoaderProps> = ({ size = 'md', color = 'white', className = '' }) => {
  const dims: Record<string, number> = { xs: 12, sm: 14, md: 16, lg: 20, xl: 24 };
  const dim = dims[size] || dims.md;
  return (
    <svg
      width={dim}
      height={dim}
      viewBox="0 0 50 50"
      className={className}
      aria-hidden="true"
    >
      <circle
        cx="25"
        cy="25"
        r="20"
        fill="none"
        stroke={color}
        strokeWidth="5"
        strokeLinecap="round"
        strokeDasharray="31.4 31.4"
      >
        <animateTransform
          attributeName="transform"
          type="rotate"
          from="0 25 25"
          to="360 25 25"
          dur="0.9s"
          repeatCount="indefinite"
        />
      </circle>
    </svg>
  );
};

interface ButtonProps {
  children: React.ReactNode;
  variant?: 'primary' | 'secondary' | 'success' | 'delete' | 'outline' | 'transparent' | 'cancel';
  size?: 'xs' | 'sm' | 'md' | 'lg';
  className?: string;
  disabled?: boolean;
  loading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  type?: 'button' | 'submit' | 'reset';
  fullWidth?: boolean;
}

const Button: React.FC<
  ButtonProps & React.ButtonHTMLAttributes<HTMLButtonElement>
> = ({
  children,
  variant = 'primary',
  size = 'md',
  className = '',
  disabled = false,
  loading = false,
  leftIcon = null,
  rightIcon = null,
  onClick,
  type = 'button',
  fullWidth = false,
  ...props
}) => {
  const variants = {
    transparent: '',
    cancel: 'border border-[#C4C8E2] bg-[#E9EBF5] hover:bg-[#D6D8E5] text-[#44475A]',
    primary: 'bg-[linear-gradient(90deg,#6A5AF9_0%,#8364FF_100%)] hover:bg-[linear-gradient(90deg,#5948E6_0%,#7354F0_100%)] text-white',
    secondary: 'bg-gray-600 hover:bg-gray-700 text-white',
    success: 'bg-green-600 hover:bg-green-700 text-white',
    delete: 'bg-[#F85A5A] hover:bg-[#E14848] text-white',
    outline: 'border-[1.5px] border-[#6A5AF9] text-[#6A5AF9] hover:bg-[#F4F3FF] font-medium',
  };

  const sizes = {
    xs: 'px-3 py-1 text-xs',
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2 text-md font-normal',
    lg: 'px-6 py-3 text-lg',
  };

  const loaderSizes: Record<string, 'xs' | 'sm' | 'md' | 'lg' | 'xl'> = {
    xs: 'xs',
    sm: 'sm',
    md: 'md',
    lg: 'lg',
  };

  const buttonClasses = clsx(
    'inline-flex items-center justify-center font-medium rounded-md text-sm',
    'focus:outline-none focus-visible:outline-none active:outline-none',
    variant && variants[variant],
    size && sizes[size],
    disabled && 'opacity-50 cursor-not-allowed',
    loading && 'pointer-events-none',
    fullWidth && 'w-full',
    className
  );

  return (
    <button
      className={buttonClasses}
      disabled={disabled || loading}
      onClick={onClick}
      type={type}
      {...props}
    >
      {loading && (
        <Loader
          size={loaderSizes[size]}
          color="white"
          className="mr-2"
          type="spinner"
        />
      )}

      {leftIcon && !loading && <span className="mr-2">{leftIcon}</span>}

      <span>{children}</span>

      {rightIcon && <span className="ml-2">{rightIcon}</span>}
    </button>
  );
};

export default Button;
