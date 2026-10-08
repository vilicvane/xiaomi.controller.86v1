import {
  ArrowRight,
  Check,
  CircleAlert,
  CodeXml,
  Download,
  Image as ImageIcon,
  LoaderCircle,
  RefreshCw,
  Save,
  Settings2,
  Timer,
  Upload,
  Wifi,
  createElement,
  type IconNode,
} from "lucide";

const icons = {
  panel: ImageIcon,
  upload: Upload,
  arrow: ArrowRight,
  image: ImageIcon,
  download: Download,
  code: CodeXml,
  wifi: Wifi,
  check: Check,
  loading: LoaderCircle,
  error: CircleAlert,
  refresh: RefreshCw,
  save: Save,
  timer: Timer,
  settings: Settings2,
} satisfies Record<string, IconNode>;

export const icon = (name: keyof typeof icons) =>
  createElement(icons[name], {
    "stroke-width": 1.65,
    "aria-hidden": "true",
    class: "lucide",
  }).outerHTML;
