"use client";

import { motion, type HTMLMotionProps, type Variants } from "motion/react";

type MotionTag = keyof typeof motion;

interface FadeInProps extends HTMLMotionProps<"div"> {
  delay?: number;
  duration?: number;
  y?: number;
  as?: MotionTag;
}

function FadeIn({
  children,
  delay = 0,
  duration = 0.4,
  y = 12,
  as = "div",
  className,
  ...props
}: FadeInProps) {
  const Comp = motion[as] as typeof motion.div;
  return (
    <Comp
      initial={{ opacity: 0, y }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration, delay, ease: "easeOut" }}
      className={className}
      {...props}
    >
      {children}
    </Comp>
  );
}

interface FadeInCardProps extends HTMLMotionProps<"div"> {
  delay?: number;
  duration?: number;
}

function FadeInCard({
  children,
  delay = 0,
  duration = 0.4,
  className,
  ...props
}: FadeInCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration, delay, ease: "easeOut" }}
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  );
}

const staggerContainerVariants = (staggerDelay: number): Variants => ({
  hidden: {},
  visible: { transition: { staggerChildren: staggerDelay } },
});

const staggerItemVariants: Variants = {
  hidden: { opacity: 0, y: 10 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.35, ease: "easeOut" },
  },
};

interface StaggerContainerProps extends HTMLMotionProps<"div"> {
  staggerDelay?: number;
}

function StaggerContainer({
  children,
  staggerDelay = 0.06,
  className,
  ...props
}: StaggerContainerProps) {
  return (
    <motion.div
      variants={staggerContainerVariants(staggerDelay)}
      initial="hidden"
      animate="visible"
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  );
}

function StaggerItem({
  children,
  className,
  ...props
}: HTMLMotionProps<"div">) {
  return (
    <motion.div variants={staggerItemVariants} className={className} {...props}>
      {children}
    </motion.div>
  );
}

export { FadeIn, FadeInCard, StaggerContainer, StaggerItem };
