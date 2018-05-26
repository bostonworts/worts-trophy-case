Rails.application.routes.draw do
  passwordless_for :users

  root "trophies#index"

  resources :trophies, only: [:create, :index, :new]
end
