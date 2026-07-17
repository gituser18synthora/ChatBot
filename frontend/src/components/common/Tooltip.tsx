import React, { useId } from 'react';
import { Tooltip as ReactTooltip, PlacesType, VariantType } from 'react-tooltip';

interface TooltipProps {
  children: React.ReactNode;
  content: React.ReactNode;
  place?: PlacesType;
  variant?: VariantType;
  className?: string;
  classNameArrow?: string;
  style?: React.CSSProperties;
  border?: string;
  opacity?: number;
  arrowColor?: string;
  arrowSize?: number;
  noArrow?: boolean;
  id?: string;
  offset?: number;
  delayShow?: number;
  delayHide?: number;
  float?: boolean;
  hidden?: boolean;
  clickable?: boolean;
  openOnClick?: boolean;
  positionStrategy?: 'absolute' | 'fixed';
  wrapper?: 'div' | 'span' | 'p';
}

const Tooltip: React.FC<TooltipProps> = ({
  children,
  content,
  place = 'right',
  variant = 'dark',
  className = '',
  classNameArrow,
  style,
  border,
  opacity,
  arrowColor,
  arrowSize,
  noArrow = false,
  id,
  offset = 10,
  delayShow = 0,
  delayHide = 0,
  float = false,
  hidden = false,
  clickable = false,
  openOnClick = false,
  positionStrategy,
  wrapper = 'div',
}) => {
  const generatedId = useId();
  const tooltipId = id || `tooltip-${generatedId}`;

  return (
    <>
      <span
        data-tooltip-id={tooltipId}
        className="inline-flex"
      >
        {children}
      </span>

      <ReactTooltip
        id={tooltipId}
        className={className}
        classNameArrow={classNameArrow}
        style={
          style || {
            backgroundColor: '#0C2D6D',
            zIndex: 999999,
            fontSize: '12px',
            borderRadius: '5px',
            maxWidth: '350px',
            whiteSpace: 'normal',
          }
        }
        variant={variant}
        place={place}
        offset={offset}
        delayShow={delayShow}
        delayHide={delayHide}
        float={float}
        hidden={hidden}
        noArrow={noArrow}
        clickable={clickable}
        openOnClick={openOnClick}
        positionStrategy={positionStrategy}
        wrapper={wrapper}
        border={border}
        opacity={opacity}
        arrowColor={arrowColor}
        arrowSize={arrowSize}
      >
        {content}
      </ReactTooltip>
    </>
  );
};

export default Tooltip;