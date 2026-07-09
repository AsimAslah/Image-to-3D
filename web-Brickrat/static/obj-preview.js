import * as THREE from "https://esm.sh/three@0.166.1";
import { OBJLoader } from "https://esm.sh/three@0.166.1/examples/jsm/loaders/OBJLoader.js";
import { OrbitControls } from "https://esm.sh/three@0.166.1/examples/jsm/controls/OrbitControls.js";

function initializeObjPreview(container) {
  if (container.dataset.initialized) return;
  container.dataset.initialized = "true";

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0c0b0a);
  const camera = new THREE.PerspectiveCamera(40, 1, 0.01, 100);
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  container.replaceChildren(renderer.domElement);

  scene.add(new THREE.HemisphereLight(0xffffff, 0x443322, 2.4));
  const keyLight = new THREE.DirectionalLight(0xffffff, 2.5);
  keyLight.position.set(3, 4, 5);
  scene.add(keyLight);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 1.5;

  function resize() {
    const width = container.clientWidth;
    const height = container.clientHeight;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }

  new ResizeObserver(resize).observe(container);
  resize();

  new OBJLoader().load(
    container.dataset.objUrl,
    (object) => {
      object.traverse((child) => {
        if (child.isMesh) {
          child.material = new THREE.MeshStandardMaterial({
            color: child.geometry.hasAttribute("color") ? 0xffffff : 0xd8b48a,
            vertexColors: child.geometry.hasAttribute("color"),
            roughness: 0.72, metalness: 0.05,
          });
        }
      });
      const box = new THREE.Box3().setFromObject(object);
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      object.position.sub(center);
      scene.add(object);

      const maxSize = Math.max(size.x, size.y, size.z);
      const distance = maxSize / (2 * Math.tan(THREE.MathUtils.degToRad(40 / 2))) * 1.18 || 2;
      camera.position.set(distance, distance * 0.65, distance);
      camera.near = Math.max(distance / 100, 0.01);
      camera.far = distance * 20;
      camera.updateProjectionMatrix();
      controls.target.set(0, 0, 0);
      controls.update();
    },
    undefined,
    () => {
      container.innerHTML = '<span class="error">OBJ preview could not be loaded.</span>';
    },
  );

  function animate() {
    if (!container.isConnected) {
      renderer.dispose();
      return;
    }
    controls.update();
    renderer.render(scene, camera);
    requestAnimationFrame(animate);
  }
  animate();
}

function initializeAll(root = document) {
  root.querySelectorAll(".obj-preview").forEach(initializeObjPreview);
}

initializeAll();
document.body.addEventListener("htmx:afterSwap", (event) => initializeAll(event.detail.target));
