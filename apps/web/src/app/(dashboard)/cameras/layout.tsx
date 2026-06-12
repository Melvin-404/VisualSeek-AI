import React from "react";

/**
 * Camera-specific layout that removes default padding
 * to let the camera grid fill the viewport.
 */
export default function CamerasLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <div className="-m-6 h-[calc(100%+3rem)]">{children}</div>;
}
