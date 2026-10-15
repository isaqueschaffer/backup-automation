# Professional Frontend Design Skill

## Purpose

Create professional, functional, consistent, and intentional frontend interfaces.

The final result should feel like it was designed and implemented by an experienced product and frontend team — not generated from a generic AI template.

Prioritize:

1. Clarity
2. Usability
3. Visual hierarchy
4. Consistency
5. Readability
6. Responsiveness
7. Professional appearance

Do not use visual trends simply because they are popular.

---

# 1. CORE PRINCIPLE

Before writing frontend code, understand the context of the interface.

Determine:

* Who will use the system?
* What is the primary purpose of the screen?
* What information is most important?
* What action does the user need to perform?
* What information must always remain visible?
* What information can be secondary?
* Is the screen used frequently or occasionally?
* Does the product require high or low information density?

The interface must be a consequence of these answers.

Do not start by choosing colors, gradients, or decorative components.

Start with structure and user experience.

---

# 2. AVOID AI-GENERATED DESIGN

The interface must NOT look like a generic AI-generated website.

Avoid patterns commonly associated with AI-generated interfaces:

* Unnecessary gradients
* Excessive glassmorphism
* Decorative blobs
* Glow effects
* Excessive shadows
* Excessive rounded cards
* Excessive border radius
* Decorative icons with no functional purpose
* Emojis as primary UI elements
* Generic startup illustrations
* Excessive hover effects
* Unnecessary animations
* Generic marketing copy
* Overly symmetrical layouts
* Generic hero sections
* Generic SaaS dashboards
* Oversized buttons
* Excessive empty space
* Visually identical components everywhere

Do not turn every piece of information into a card.

A table should remain a table.

A form should remain a form.

A navigation system should remain a navigation system.

Use visual elements because they improve usability or hierarchy — not because they make the interface look more impressive.

---

# 3. PRODUCT-DRIVEN DESIGN

The design must reflect the type of software being built.

Do not use the same visual structure for every type of application.

## Administrative systems

Prioritize:

* Information
* Tables
* Filters
* Search
* Sorting
* Status
* Quick actions
* Forms
* History
* Pagination
* Feedback

Use moderate information density.

Do not convert every record into a card.

---

## Technical systems

Prioritize:

* Status
* Indicators
* Logs
* Equipment
* Alerts
* Dates
* Identifiers
* Technical information
* Filters
* Event history

Operational information should be easy to scan.

---

## Inventory systems

Prioritize:

* Code
* Name
* Category
* Quantity
* Condition
* Responsible person
* Location
* Date
* Movements
* History

Use tables when there are many records.

---

## Project management systems

Prioritize:

* Project
* Client
* Responsible people
* Deadline
* Status
* Stages
* Tasks
* Priority
* Progress
* History

Use Kanban boards, tables, timelines, or calendars only when they improve the user's workflow.

---

## Corporate / institutional websites

Prioritize:

* Company identity
* Value proposition
* Services
* Differentiators
* Social proof
* Contact information
* Relevant information
* SEO
* Responsiveness

Do not automatically turn every website into a futuristic landing page.

---

# 4. VISUAL HIERARCHY

Every screen must have a clear visual hierarchy.

Establish different levels for:

* Page title
* Subtitle
* Primary information
* Secondary information
* Metadata
* Actions
* Alerts
* States

The user should be able to understand the purpose of the screen quickly.

Do not give every element the same visual weight.

If everything demands attention, nothing does.

---

# 5. TYPOGRAPHY

Use simple, professional, highly readable typography.

Prefer fonts such as:

* Inter
* IBM Plex Sans
* Roboto
* Source Sans 3
* Geist
* system-ui

Do not use multiple font families without a clear reason.

Normally use:

* One primary font family
* Different font weights for hierarchy

Suggested weight usage:

* 400 → normal text
* 500 → emphasized information
* 600 → headings and important elements
* 700 → major headings when appropriate

Avoid extremely large typography in internal business applications.

---

# 6. COLOR SYSTEM

Colors must have a purpose.

Define a coherent color system containing:

* Primary
* Secondary, when necessary
* Background
* Surface
* Border
* Primary text
* Secondary text
* Success
* Warning
* Error
* Info

Do not introduce many colors without a functional reason.

## Semantic states

Green:

* Success
* Active
* Completed
* Available

Yellow / orange:

* Warning
* Pending
* Waiting

Red:

* Error
* Failure
* Unavailable
* Destructive actions

Blue:

* Information
* Primary actions
* Informational states

Do not rely only on color to communicate meaning.

Combine color with:

* Text
* Icons
* Indicators
* Structure

---

# 7. SPACING

Use a consistent spacing system.

Prefer a coherent spacing scale such as:

* 4px
* 8px
* 12px
* 16px
* 20px
* 24px
* 32px
* 40px
* 48px

Avoid arbitrary spacing values throughout the application.

Spacing should help visually group related information.

---

# 8. BORDER RADIUS

Do not overuse rounded corners.

For corporate and business applications, prefer moderate values such as:

* 4px
* 6px
* 8px
* 10px

Buttons and inputs should generally use moderate rounding.

Avoid turning every component into a pill.

Pill-shaped elements should primarily be reserved for:

* Statuses
* Tags
* Categories
* Small indicators

---

# 9. SHADOWS

Use shadows subtly.

Shadows should primarily establish spatial hierarchy for:

* Modals
* Dropdowns
* Popovers
* Floating elements

Do not apply strong shadows to every card.

Many professional interfaces can rely primarily on:

* Background
* Surface
* Borders
* Spacing

---

# 10. CARDS

Cards are grouping tools.

Do not use cards simply because there is empty space on the screen.

Use cards for:

* Summaries
* Metrics
* Independent information groups
* Components that need visual separation

Avoid:

Card inside card inside card.

Do not place every section inside multiple layers of containers.

---

# 11. TABLES

When displaying many records, prefer tables.

A professional table should have:

* Clear headers
* Relevant columns
* Consistent alignment
* Appropriate spacing
* Status indicators
* Actions
* Subtle hover states
* Pagination when necessary
* Sorting when useful
* Search and filters when useful

Do not add columns simply to fill space.

Avoid visually overloaded tables.

Prioritize scanability.

---

# 12. FORMS

Forms should be predictable and easy to understand.

Each field should normally contain:

* Label
* Appropriate input
* Placeholder only when useful
* Error state
* Helper text when necessary

Never use placeholders as a replacement for labels.

Group related fields together.

Example:

## Equipment information

* Name
* Category
* Serial number

## Responsibility

* Technician
* City
* Assignment date

Use multiple columns when they improve readability.

Do not create a single extremely long column when the information can be organized more efficiently.

---

# 13. BUTTONS

Buttons must communicate their action clearly.

Use a clear hierarchy:

### Primary

The main action.

Example:

Save

### Secondary

Alternative action.

Example:

Cancel

### Tertiary

Low-priority action.

### Destructive

Actions such as:

* Delete
* Remove
* Permanently cancel

Do not create multiple primary buttons competing with each other.

The primary action should be visually obvious.

---

# 14. NAVIGATION

Navigation should reflect the actual structure of the product.

For larger administrative systems, a sidebar is appropriate when there are multiple functional areas.

Example:

* Dashboard
* Projects
* Clients
* Equipment
* Tasks
* Inventory
* Reports
* Settings

Do not add navigation items simply to make the interface look more complete.

Navigation should provide:

* Active state
* Clear hierarchy
* Logical grouping
* Clear labels
* Icons when useful

---

# 15. DASHBOARDS

Do not create dashboards consisting only of four statistic cards.

A dashboard should answer useful questions.

Examples:

* What is happening?
* What needs attention?
* What changed?
* What is overdue?
* What is pending?
* What should the user do next?

Use:

* Metrics
* Tables
* Charts when useful
* Recent activity
* Alerts
* Pending tasks

Do not use charts merely for decoration.

---

# 16. UI STATES

Every data-driven screen must consider:

## Loading

Provide an appropriate loading state.

Do not leave the interface looking broken while data is loading.

## Empty state

When there are no records, clearly explain:

* What happened
* What the user can do next

Example:

"There are no tools registered yet."

"Register the first tool to get started."

## Error state

Explain errors in understandable language.

Avoid generic messages such as:

"Something went wrong."

Provide useful context whenever possible.

## Success state

Confirm important actions.

Example:

"Tool successfully registered."

---

# 17. USER FEEDBACK

Important actions must provide feedback.

Examples:

* Save
* Delete
* Update
* Assign
* Complete
* Import
* Export

Use the appropriate feedback mechanism:

* Toast
* Alert
* Modal
* Inline state
* Loading state

Do not create a modal for every action.

---

# 18. RESPONSIVENESS

The interface must work across:

* Desktop
* Tablet
* Mobile

Do not simply shrink desktop layouts.

Adapt the structure to the available screen size.

Example:

Desktop:

Sidebar + content

Mobile:

Header + menu + content

For tables on mobile:

* Use horizontal scrolling when appropriate
* Prioritize important columns
* Consider transforming records into a mobile-friendly layout when necessary

Never allow important information to be silently cut off.

---

# 19. ACCESSIBILITY

Prioritize:

* Sufficient contrast
* Labels
* Visible focus states
* Keyboard navigation
* Semantic HTML
* Real `<button>` elements for actions
* Real `<a>` elements for navigation
* Properly associated labels and inputs
* `aria-label` only when necessary

Never rely exclusively on color to communicate information.

---

# 20. ICONS

Icons must have a purpose.

Prefer consistent icon libraries such as:

* Lucide
* Material Symbols
* Phosphor

Do not mix multiple icon styles without a clear reason.

Do not use emojis as replacements for professional UI icons.

Avoid oversized icons.

---

# 21. ANIMATIONS

Animations must have a purpose.

Use animation primarily for:

* Transitions
* Feedback
* Loading
* Enter/exit states
* State changes

Avoid:

* Bouncing elements
* Excessive effects
* Unnecessary parallax
* Continuous animations
* Animated glow
* Movement purely for visual impressiveness

Professional interfaces generally use motion subtly.

---

# 22. MICROINTERACTIONS

Use microinteractions to improve usability.

Examples:

* Hover
* Focus
* Active
* Disabled
* Loading
* Success

They should be fast and subtle.

---

# 23. LAYOUT

Prefer simple, structured layouts.

Use:

* CSS Grid
* Flexbox
* Containers
* Sections
* Columns
* Rows

Avoid unnecessarily complex structures.

The composition should feel intentional.

---

# 24. INFORMATION DENSITY

Density depends on the product.

Administrative system:

Moderate to high.

Institutional website:

Moderate to low.

Technical system:

Moderate to high.

Do not create huge empty areas in applications that need to present significant amounts of information.

Do not compress information unnecessarily either.

---

# 25. CONTENT

Do not use generic copy.

Avoid:

* Lorem ipsum
* Generic startup slogans
* Generic AI marketing copy
* Meaningless placeholder text

Use content that makes sense for the actual domain.

If the application manages inventory, use inventory terminology.

If it manages projects, use project terminology.

If it manages equipment, use equipment terminology.

All user-facing text should be written in **Brazilian Portuguese** unless the project explicitly requires another language.

Use natural Brazilian Portuguese.

---

# 26. COMPONENT ARCHITECTURE

Create reusable components.

Examples:

* Button
* Input
* Select
* Modal
* Toast
* Badge
* Table
* Sidebar
* Header
* EmptyState
* Loading
* ConfirmDialog

Do not duplicate visually identical components across multiple screens.

If two components have the same behavior and appearance, consider reusing the same component.

---

# 27. DESIGN TOKENS

Centralize visual values.

Example:

```css
:root {
  --color-primary: ...;
  --color-background: ...;
  --color-surface: ...;
  --color-border: ...;
  --color-text: ...;
  --color-text-secondary: ...;

  --spacing-1: 4px;
  --spacing-2: 8px;
  --spacing-3: 12px;
  --spacing-4: 16px;
  --spacing-5: 24px;
  --spacing-6: 32px;

  --radius-small: 4px;
  --radius-medium: 8px;

  --shadow-subtle: ...;
}
```

Use these values consistently.

Do not create arbitrary visual values throughout the project.

---

# 28. DARK MODE

Dark mode must not simply be:

```css
background: black;
color: white;
```

Use multiple surface levels.

For example:

* Background
* Surface
* Elevated surface
* Border
* Primary text
* Secondary text

Avoid pure white text everywhere.

---

# 29. DESKTOP-FIRST FOR INTERNAL SYSTEMS

When the product is primarily used by employees on computers:

Prioritize desktop.

Then adapt the interface for tablets and mobile.

When the product is primarily mobile:

Prioritize mobile.

The strategy must reflect actual usage.

---

# 30. VISUAL REFERENCES

When the user provides a website, image, or visual reference:

Do not copy it literally.

Analyze:

* Hierarchy
* Typography
* Spacing
* Organization
* Navigation
* Image treatment
* Components
* Density
* Visual language

Then adapt those principles to the current product.

---

# 31. EXISTING PROJECT CONSISTENCY

Before implementing a new screen:

Inspect the existing project.

Understand:

* Existing components
* Existing design tokens
* Existing typography
* Existing colors
* Existing spacing
* Existing navigation
* Existing interaction patterns

Reuse the existing design system whenever appropriate.

Do not redesign the entire application when implementing a single feature.

A new screen must feel like part of the same product.

---

# 32. DEVELOPMENT PROCESS

Before implementing a new interface:

1. Understand the goal.
2. Identify the user and workflow.
3. Define the information hierarchy.
4. Define the layout.
5. Define reusable components.
6. Define interaction states.
7. Implement the interface.
8. Review the visual result.
9. Review responsiveness.
10. Review accessibility.
11. Remove unnecessary visual elements.

Do not start with decorative CSS.

---

# 33. MANDATORY VISUAL REVIEW

After implementing an interface, review it.

## Hierarchy

* Is the user's current location clear?
* Is the page title clear?
* Is the primary action obvious?
* Is important information visually prioritized?

## Layout

* Is there excessive empty space?
* Is information too compressed?
* Are alignments consistent?

## Components

* Are there unnecessary cards?
* Are there too many buttons?
* Are there decorative elements without a purpose?

## Typography

* Are font sizes consistent?
* Is the contrast sufficient?
* Is secondary information visually secondary?

## Colors

* Do colors have a purpose?
* Are there too many colors?
* Is contrast sufficient?

## Responsiveness

* Does the interface work at different widths?
* Are tables usable?
* Do forms adapt correctly?
* Does navigation adapt correctly?

## Overall appearance

Ask:

"Does this look like professional software designed for real users?"

If not, simplify and reorganize before adding visual effects.

---

# 34. SIMPLICITY RULE

When choosing between adding or removing a visual element:

Prefer the simplest solution that preserves usability and information.

Do not add:

* Shadows
* Gradients
* Animations
* Icons
* Cards
* Badges
* Borders
* Decorative elements

without a functional, semantic, or hierarchical reason.

---

# 35. DESIGN DECISION RULE

When multiple visual approaches are possible, choose based on:

1. User workflow
2. Information hierarchy
3. Product context
4. Consistency with the existing interface
5. Accessibility
6. Maintainability
7. Visual refinement

Do not choose an approach simply because it looks impressive in a screenshot.

The interface must work well in real usage.

---

# 36. IMPLEMENTATION QUALITY

Visual quality and code quality must work together.

Prefer:

* Semantic HTML
* Reusable components
* Clear component boundaries
* Maintainable CSS
* Consistent naming
* Responsive layouts
* Accessible interactions
* Minimal duplication

Do not sacrifice maintainability for visual effects.

Do not create unnecessary abstractions solely for the sake of abstraction.

---

# 37. FINAL PRINCIPLE

Do not try to impress the user with the design.

Make the user feel that the software is:

* Clear
* Fast
* Organized
* Reliable
* Consistent
* Professional

The design should feel like a natural consequence of the product.

The interface should not look "AI-generated".

It should look like it was specifically designed for the business, the workflow, and the people using it.
